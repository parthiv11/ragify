import time
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from airbyte import get_source, get_available_connectors
import mindsdb_sdk as mdb
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import uuid
from typing import Dict, Optional, List
import os
from dotenv import load_dotenv
import shutil
import duckdb

# Load environment variables
load_dotenv()

# Initialize FastAPI
app = FastAPI(title="AI Agent with MindsDB + Airbyte")

# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint to verify API availability"""
    try:
        # Verify MindsDB connection
        server_info = server.status()
        return {
            "status": "ok",
            "message": "API is operational",
            "mindsdb_status": "connected",
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"API health check failed: {str(e)}",
            "mindsdb_status": "disconnected",
            "timestamp": datetime.datetime.utcnow().isoformat()
        }

# Connect to MindsDB
while True:
    try:
        server = mdb.connect()
        project = server.get_project(os.getenv('MINDSDB_PROJECT', 'mindsdb'))
        break
    except Exception as e:
        time.sleep(5)  # Retry after 5 seconds
        print(f"Error connecting to MindsDB: {e}")
        print(f"Retrying connection to MindsDB...")
        # raise RuntimeError(f"Error connecting to MindsDB: {e}")
        

# Model Configuration from environment
DEFAULT_AGENT_NAME = os.getenv('DEFAULT_AGENT_NAME', 'universal_agent')
DEFAULT_MODEL_NAME = os.getenv('AGENT_MODEL_NAME', 'gpt-4o-mini')
DEFAULT_PROMPT = os.getenv('AGENT_MODEL_PROMPT', 
    "Answer the user's question in a helpful way using the available skills when relevant: {{question}}")

# Model parameters
MODEL_CONFIG = {
    'provider': os.getenv('AGENT_MODEL_PROVIDER', 'google'),
    'max_tokens': int(os.getenv('AGENT_MODEL_MAX_TOKENS', 1000)),
    'temperature': float(os.getenv('AGENT_MODEL_TEMPERATURE', 0.7)),
}

# Embedding model configuration
EMBEDDING_CONFIG = {
    'model': os.getenv('EMBEDDING_MODEL_NAME', 'sentence-transformers/all-mpnet-base-v2'),
    'provider': os.getenv('EMBEDDING_MODEL_PROVIDER', 'huggingface'),
    'max_length': int(os.getenv('EMBEDDING_MODEL_MAX_LENGTH', 512))
}

# Ensure the embedding and ml_engine model exists
try:
    langchain_ml_engine = server.ml_engines.get("embedding")
except Exception:
    langchain_ml_engine = server.ml_engines.create(
        name="embedding",
        handler="langchain_embedding",
    )
try:
    embedding_model = server.models.get("hf_embedding_model")
except Exception:
    embedding_model = server.models.create(
        name="hf_embedding_model",
        engine="embedding",
        options={
            "model": EMBEDDING_CONFIG['model'],
            "class": "HuggingFaceEmbeddings",
        },
        predict="embedding",
    )


# Ensure default agent exists with configured parameters
try:
    agent = project.agents.get(DEFAULT_AGENT_NAME)
except Exception:
    agent = project.agents.create(
        name=DEFAULT_AGENT_NAME,
        model=DEFAULT_MODEL_NAME,
        skills=[],
        params={
            "prompt_template": DEFAULT_PROMPT,
            "max_tokens": MODEL_CONFIG['max_tokens'],
            "temperature": MODEL_CONFIG['temperature'],
            "provider": MODEL_CONFIG['provider'],
            "openai_api_key": os.getenv('OPENAI_API_KEY', ''),
            "base_url": os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1'),
            
        }
    )

# Database setup (SQLite for simplicity)
DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Define the KB Registry table model
class KBRegistry(Base):
    __tablename__ = "kb_registry"
    
    id = Column(Integer, primary_key=True, index=True)
    kb_name = Column(String, index=True)
    alias = Column(String)
    agent_name = Column(String)
    source_name = Column(String)
    user_source_name = Column(String)
    source_description = Column(String)
    streams_used = Column(JSON)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Create the table 
Base.metadata.create_all(bind=engine)

# Session-like storage (for demo/testing)
session = {
    "source": None,
    "streams": [],
    "kb": None,
    "agent": None
}

# Helper functions for skills management
def get_or_create_kb_skill(kb_name: str, description: str) -> Optional[str]:
    """Gets or creates a KB skill, returns skill name"""
    skill_name = f"kb_skill_{kb_name}"  # Simplified KB skill name
    try:
        # Try to find existing skill for this KB
        existing_skills = [s for s in server.skills.list() if 
                         s.type == 'retrieval' and 
                         s.params.get('source') == kb_name]
        if existing_skills:
            return existing_skills[0].name
            
        # Create new skill
        skill = project.skills.create(
            name=skill_name,
            type='retrieval',
            params={
                'source': kb_name,
                'description': description
            }
        )
        return skill.name
    except Exception as e:
        print(f"Error with KB skill: {e}")
        return None

def get_or_create_db_skill(db_name: str, description: str) -> Optional[str]:
    """Gets or creates a DB skill, returns skill name"""
    skill_name = f"db_skill_{db_name}"  # Simplified DB skill name
    try:
        # Try to find existing skill for this DB
        existing_skills = [skill for skill in server.skills.list() if
                         skill.type == 'sql' and
                         skill.params.get('database') == db_name]
        if existing_skills:
            return existing_skills[0].name
            
        # Create new skill
        db = server.databases.get(db_name)
        tables = [t.name for t in db.tables.list()]
        
        skill = project.skills.create(
            name=skill_name,
            type='sql',
            params={
                'database': db_name,
                'tables': tables,
                'description': description
            }
        )
        return skill.name
    except Exception as e:
        print(f"Error with DB skill: {e}")
        return None

# Helper function for consistent database naming
def normalize_db_name(source_name: str) -> str:
    """Generate consistent database name from source name.
    Converts user source name to a valid database name by:
    - Converting to lowercase
    - Replacing hyphens and spaces with underscores
    - Adding _db suffix
    """
    return f"{source_name.lower().replace('-', '_').replace(' ', '_')}_db"

# ---------------------------
# 1. List available connectors
# ---------------------------
@app.get("/list_sources")
def list_sources():
    sources = [i for i in get_available_connectors() if i.startswith("source-")]
    return {"available_sources": sources}

# ---------------------------
# 2. Get source specification
# ---------------------------
@app.get("/source_spec/{source_name}")
def get_source_spec(source_name: str):
    try:
        session['source'] = get_source(source_name, config={})
        return {"source_spec": session['source']._get_spec()}
    except Exception as e:
        return {"error": str(e)}

# ---------------------------
# 3. Configure a data source
# ---------------------------
class SourceConfig(BaseModel):
    source_name: str
    config: dict

@app.post("/set_source_config")
def set_source_config(data: SourceConfig):
    try:
        session['source'].set_config(data.config)
        session['source'].check()
        return {"message": "Source configured"}
    except Exception as e:
        return {"error": f"Failed to configure source: {e}"}

# ---------------------------
# 4. Fetch available streams
# ---------------------------
@app.get("/streams")
def fetch_streams():
    if not session["source"]:
        return {"error": "Source not configured"}
    try:
        return {"available_streams": session["source"].get_available_streams()}
    except Exception as e:
        return {"error": str(e)}

@app.get("/fetch_schema")
def fetch_schema():
    if not session["source"]:
        return {"error": "Source not configured"}
    if not session["streams"]:
        return {"error": "No streams selected"}

    try:
        session["source"].set_streams(session["streams"])
        catalog = session["source"].discovered_catalog
        if not catalog or not catalog.streams:
            return {"error": "No streams found in the catalog"}

        records = {}
        for stream in catalog.streams:
            schema = stream.json_schema.get('properties', {})
            records[stream.name]=schema
        if not records:
            return {"error": "No schemas available for the selected streams"}
        return {"records": records}
    except Exception as e:
        return {"error": f"Failed to fetch schema: {e}"}

# ---------------------------
# 5. Select streams to use
# ---------------------------
class StreamSelection(BaseModel):
    streams: list

@app.post("/select_streams")
def select_streams(data: StreamSelection):
    try:
        session["streams"] = data.streams or session["source"].get_available_streams()
        session["source"].set_streams(session["streams"])
        return {"message": "Streams selected", "streams": session["streams"]}
    except Exception as e:
        return {"error": str(e)}

# ---------------------------
# 6. Ingest data into MindsDB knowledge base
# ---------------------------
class IngestData(BaseModel):
    source_name: str
    user_source_name: str
    source_description: str = ""
    streams: list
    metadata_columns: dict = None  # Dictionary mapping stream name to list of metadata columns
    content_columns: dict = None   # Dictionary mapping stream name to list of content columns

@app.post("/create_kb")
def create_kb(data: IngestData):
    session['streams'] = data.streams
    if not session["streams"]:
        return {"error": "No streams selected"}

    db = SessionLocal()
    created_kbs = []
    created_dbs = []
    source_prefix = data.user_source_name.lower().replace('-', '_').replace(' ', '_')
    try:
        session["source"].set_streams(session["streams"])
        read_result = session["source"].read()
        
        # Handle the DuckDB cache file for the source DB
        db_name = normalize_db_name(data.source_name)  # Use user_source_name here
        if hasattr(read_result, '_cache') and read_result._cache:
            # Create a temporary copy of the DuckDB file
            temp_db_path = f"/tmp/{db_name}.duckdb"
            cache_path = read_result._cache.db_path
            if db_name not in created_dbs:  # Only create DB once per source
                shutil.copy2(cache_path, temp_db_path)
                con=duckdb.connect(temp_db_path)
                tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
                table_to_drop = [t for t in tables if t.startswith("airbyte_") or t not in data.streams]
                for t in table_to_drop:
                    con.execute(f"DROP TABLE {t}")
                con.close()
                # Create the database in MindsDB

                try:
                    server.databases.create(
                        db_name,
                        engine='duckdb',
                        connection_args={
                            'database': temp_db_path
                        }
                    )
                    created_dbs.append(db_name)
                except Exception as e:
                    if e.args[0].startswith("Database already exists"):
                        server.databases.drop(db_name)
                        server.databases.create(
                            db_name,
                            engine='duckdb',
                            connection_args={
                                'database': temp_db_path
                            }
                        )
                        created_dbs.append(db_name)
                    else:
                        print(f"Error creating datasource: {e}")
            
        # Get list of existing KBs
        kbs = [i.name for i in server.knowledge_bases.list()]
        try:
            hf_embedding_model = server.models.hf_embedding_model
        except Exception as e:
            # create the embedding model if it doesn't exist
            hf_embedding_model = server.models.create(
                name="hf_embedding_model",
                type="embedding",
                provider="huggingface",
                model=EMBEDDING_CONFIG['model'],
                params={
                    "max_length": EMBEDDING_CONFIG['max_length'],
                    "provider": EMBEDDING_CONFIG['provider']
                }
            )
        
        for stream in session["streams"]:
            # New naming convention
            kb_name = f"{source_prefix}_{stream.lower().replace(' ', '_')}_kb"
            
            
            # Check if KB already exists in our local database
            existing_kb = db.query(KBRegistry).filter(KBRegistry.kb_name == kb_name).first()
            if existing_kb:
                continue
                
            try:
                # Create Knowledge Base if it doesn't exist
                if kb_name not in kbs:
                    kb = server.knowledge_bases.create(
                        kb_name,
                        metadata_columns=data.metadata_columns.get(stream, []),
                        content_columns=data.content_columns.get(stream, []),
                        model=server.models.hf_embedding_model,
                        id_column="id",
                    )
                else:
                    kb = server.knowledge_bases.get(kb_name)

                records = read_result[stream]
                df = records.to_pandas()
                
                
                # Convert all Timestamps to ISO string format for KB insertion
                for col in df.columns:
                    if pd.api.types.is_datetime64_any_dtype(df[col]):
                        df[col] = df[col].astype(str)
                
                # Convert DataFrame to SQL insert statements for MindsDB
                table_name = kb_name
                columns = df.columns.tolist()
                values_list = []
                
                for _, row in df.iterrows():
                    values = []
                    for col in columns:
                        val = row[col]
                        if pd.isna(val):
                            values.append('NULL')
                        elif isinstance(val, (int, float)):
                            values.append(str(val))
                        else:
                            val = str(val).replace("'", "''")
                            values.append(f"'{val}'")
                    values_list.append(f"({', '.join(values)})")

                # Create batch insert query for KB
                insert_query = f"""
                INSERT INTO {table_name} 
                ({', '.join(columns)})
                VALUES
                {', '.join(values_list)}
                """
                
                # Execute the insert query
                server.query(insert_query).fetch()
                
                # Only after successful ingestion, add to local DB with user-defined names
                db.add(KBRegistry(
                    kb_name=kb_name,
                    alias=stream,
                    agent_name=f"agent_{stream.lower().replace(' ', '_')}",
                    source_name=data.source_name,
                    user_source_name=data.user_source_name,
                    source_description=data.source_description,
                    streams_used=[stream]
                ))
                db.commit()
                
                created_kbs.append(kb_name)
                
            except Exception as e:
                db.rollback()
                print(f"Error processing stream {stream}: {e}")
                continue

        session["kb"] = created_kbs[-1] if created_kbs else None
        
        message = f"Data ingested into knowledge bases: {', '.join(created_kbs)}" if created_kbs else "No new knowledge bases created"
        if created_dbs:
            message += f"\nCreated SQL databases: {', '.join(created_dbs)}"
            
        return {"message": message}
        
    except Exception as e:
        db.rollback()
        return {"error": f"Ingestion failed: {e}"}
    finally:
        db.close()

# ---------------------------
# 7. Ask a question to the agent
# ---------------------------
class Question(BaseModel):
    query: str
    kb_name: Optional[str] = None  # Optional now
    agent_name: Optional[str] = None  # New field

@app.post("/ask")
def ask_agent(q: Question):
    try:
        response = agent.completion([{
            'question': q.query,
            'answer': None
        }])
        return {
            'status': 'success',
            'response': response.content,
            'context': response.context if hasattr(response, 'context') else None
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

# ---------------------------
# 8. Create and manage agent skills
# ---------------------------
class AgentSkillsData(BaseModel):
    kb_names: list[str]  # List of knowledge base names to use
    db_names: list[str]  # List of database names to use for SQL skills
    model_name: str = "my_model"  # Default model name

@app.post("/create_agent_skills")
def create_agent_skills(data: AgentSkillsData):
    try:
        new_skills = []
        skill_mapping = {'kbs': [], 'dbs': []}
        warnings = []
        errors = []

        # Process knowledge bases
        for kb_name in data.kb_names:
            try:
                skill_name = get_or_create_kb_skill(kb_name, f"Knowledge from {kb_name}")
                if skill_name:
                    new_skills.append(skill_name)
                    skill_mapping['kbs'].append({'kb': kb_name, 'skill': skill_name})
            except Exception as e:
                if "already exists" in str(e):
                    warnings.append(f"KB skill for {kb_name} already exists and will be reused")
                else:
                    errors.append(f"Failed to create KB skill for {kb_name}: {str(e)}")

        # Process databases
        for db_name in data.db_names:
            try:
                # First verify DB exists
                try:
                    server.databases.get(db_name)
                except Exception as e:
                    errors.append(f"Database '{db_name}' does not exist. Make sure to create it first.")
                    continue

                skill_name = get_or_create_db_skill(db_name, f"SQL access to {db_name} database")
                if skill_name:
                    new_skills.append(skill_name)
                    skill_mapping['dbs'].append({'db': db_name, 'skill': skill_name})
            except Exception as e:
                errors.append(f"Failed to create DB skill for {db_name}: {str(e)}")

        # Update agent if we have any valid skills
        if new_skills:
            current_skills = set(s.name for s in agent.skills)
            new_skills_set = set(s for s in new_skills)
            
            skills_to_add = list(new_skills_set - current_skills)
            skills_to_remove = list(current_skills - new_skills_set)
            
            # Update agent's skills
            agent.skills = [server.skills.get(i) for i in new_skills]
            server.agents.update(agent.name, agent)

            return {
                'status': 'success',
                'agent_name': DEFAULT_AGENT_NAME,
                'skills_added': skills_to_add,
                'skills_removed': skills_to_remove,
                'skill_mapping': skill_mapping,
                'warnings': warnings,
                'errors': errors
            }
        else:
            return {
                'status': 'error',
                'error': 'No valid skills could be created',
                'details': errors
            }
            
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

@app.post("/cleanup_skills")
def cleanup_unused_skills():
    try:
        all_skills = project.skills.list()
        agent_skills = set(s.name for s in agent.skills)
        
        removed = []
        for skill in all_skills:
            if skill.name not in agent_skills:
                try:
                    project.skills.drop(skill.name)
                    removed.append(skill.name)
                except Exception as e:
                    print(f"Error removing skill {skill.name}: {e}")

        return {
            'status': 'success',
            'message': f"Removed {len(removed)} unused skills",
            'removed_skills': removed
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

# ---------------------------
# 9. (Optional) Upload files for local use
# ---------------------------
@app.post("/upload_file")
async def upload_file(file: UploadFile = File(...)):
    contents = await file.read()
    with open(f"./{file.filename}", "wb") as f:
        f.write(contents)
    return {"filename": file.filename, "message": "File uploaded successfully"}

@app.get("/list_kbs")
def list_kbs():
    db = SessionLocal()
    try:
        kbs = db.query(KBRegistry).all()
        return [{"kb_name": kb.kb_name, 
                "alias": kb.alias,
                "agent_name": kb.agent_name,
                "source_name": kb.source_name,
                "streams_used": kb.streams_used,
                "created_at": kb.created_at} for kb in kbs]
    finally:
        db.close()

# ---------------------------
# Source Deletion
# ---------------------------
@app.delete("/delete_source/{source_name}")
def delete_source(source_name: str):
    """Delete a source and all its associated resources"""
    db = SessionLocal()
    try:
        # Find all KBs associated with this source
        kbs = db.query(KBRegistry).filter(
            (KBRegistry.source_name == source_name) | 
            (KBRegistry.user_source_name == source_name)
        ).all()
        
        # Delete KBs from MindsDB
        for kb in kbs:
            try:
                # Delete KB skills first
                skill_name = f"kb_skill_{kb.kb_name}"
                try:
                    project.skills.drop(skill_name)
                except Exception as e:
                    print(f"Error deleting skill {skill_name}: {e}")
                
                # Delete the KB
                try:
                    server.knowledge_bases.drop(kb.kb_name)
                except Exception as e:
                    print(f"Error deleting KB {kb.kb_name}: {e}")
            except Exception as e:
                print(f"Error processing KB {kb.kb_name}: {e}")

        # Delete associated database - use user_source_name from the KB
        if kbs:
            db_name = normalize_db_name(kbs[0].user_source_name)
        else:
            # Fallback to source_name if no KB found
            db_name = normalize_db_name(source_name)
            
        try:
            server.databases.drop(db_name)
        except Exception as e:
            print(f"Error deleting database {db_name}: {e}")

        # Delete KB records from our registry
        db.query(KBRegistry).filter(
            (KBRegistry.source_name == source_name) | 
            (KBRegistry.user_source_name == source_name)
        ).delete()
        db.commit()

        return {"message": f"Source {source_name} and all associated resources deleted successfully"}
    except Exception as e:
        db.rollback()
        return {"error": f"Failed to delete source: {str(e)}"}
    finally:
        db.close()
