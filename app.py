import streamlit as st
import requests
import time
from datetime import datetime

API_URL = "http://localhost:8000"

# Page config with wide layout
st.set_page_config(
    page_title="Ragify",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Session State Setup ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "kbs" not in st.session_state:
    st.session_state.kbs = []
if "selected_source" not in st.session_state:
    st.session_state.selected_source = None
if "current_step" not in st.session_state:
    st.session_state.current_step = 1
if "selected_resources" not in st.session_state:
    st.session_state.selected_resources = {'kbs': [], 'dbs': []}

# Add source-related session states
if "source_name" not in st.session_state:
    st.session_state.source_name = None
if "user_source_name" not in st.session_state:
    st.session_state.user_source_name = None
if "source_description" not in st.session_state:
    st.session_state.source_description = None
if "config_values" not in st.session_state:
    st.session_state.config_values = None
if "selected_streams" not in st.session_state:
    st.session_state.selected_streams = []

# Initialize other session states...
if "source_selected" not in st.session_state:
    st.session_state.source_selected = False
if "source_configured" not in st.session_state:
    st.session_state.source_configured = False
if "streams_fetched" not in st.session_state:
    st.session_state.streams_fetched = False
if "agent_ready" not in st.session_state:
    st.session_state.agent_ready = False
if "current_kb" not in st.session_state:
    st.session_state.current_kb = None

# Add new session states for loading
if "is_loading" not in st.session_state:
    st.session_state.is_loading = False
if "loading_message" not in st.session_state:
    st.session_state.loading_message = ""
if "operation_status" not in st.session_state:
    st.session_state.operation_status = None

# --- Helper Functions ---
def get_sources():
    return requests.get(f"{API_URL}/list_sources").json()["available_sources"]

def get_source_spec(source_name):
    j = requests.get(f"{API_URL}/source_spec/{source_name}").json()
    return j.get("source_spec", j.get("error"))

def configure_source(source_name, config):
    return requests.post(f"{API_URL}/set_source_config", json={"source_name": source_name, "config": config}).json()

def get_streams():
    return requests.get(f"{API_URL}/streams").json()["available_streams"]

def select_streams(streams):
    return requests.post(f"{API_URL}/select_streams", json={"streams": streams}).json()

def create_kb(source_name, user_source_name, source_description="", streams=None, metadata_columns=None, content_columns=None):
    return requests.post(f"{API_URL}/create_kb", json={
        "source_name": source_name,
        "user_source_name": user_source_name,
        "source_description": source_description,
        "streams": streams,
        "metadata_columns": metadata_columns,
        "content_columns": content_columns
    }).json()

def create_agent(kb_name=None):
    return requests.post(f"{API_URL}/create_agent", json={"kb_name": kb_name}).json()

def ask_agent(question):
    return requests.post(f"{API_URL}/ask", json={"query": question}).json()

def fetch_schema():
    return requests.get(f"{API_URL}/fetch_schema").json()

def get_kbs():
    if not st.session_state.kbs:
        response = requests.get(f"{API_URL}/list_kbs").json()
        if isinstance(response, list):
            st.session_state.kbs = response
    return st.session_state.kbs

def create_agent_skills(kb_names, db_names):
    return requests.post(f"{API_URL}/create_agent_skills", json={
        "kb_names": kb_names,
        "db_names": db_names
    }).json()

def cleanup_skills():
    return requests.post(f"{API_URL}/cleanup_skills").json()

def show_loading(message: str):
    st.session_state.is_loading = True
    st.session_state.loading_message = message

def hide_loading():
    st.session_state.is_loading = False
    st.session_state.loading_message = ""
    
def set_operation_status(status: str, message: str):
    st.session_state.operation_status = {"status": status, "message": message}

# --- Sidebar ---
with st.sidebar:
    st.title("📚 Available Sources")
    
    # Resources and Skills Selection Section
    st.write("### 🎯 Select Skills")
    
    # Get and group sources
    kbs = get_kbs()
    sources = {}
    if kbs:
        for kb in kbs:
            user_source = kb.get('user_source_name') or kb['source_name']
            if user_source not in sources:
                sources[user_source] = {
                    'description': kb.get('source_description', ''),
                    'kbs': [],
                    'created_at': kb.get('created_at', ''),
                    'status': '🟢' if kb.get('status', 'active') == 'active' else '🔴'
                }
            sources[user_source]['kbs'].append(kb)
    
    # Skills Selection
    if sources:
        for source_name, details in sources.items():
            with st.expander(f"{details['status']} {source_name}", True):
                st.caption(f"Created: {details['created_at']}")
                if details['description']:
                    st.info(details['description'])
                
                # Knowledge Bases
                if details['kbs']:
                    st.write("📚 **Knowledge Bases**")
                    for kb in details['kbs']:
                        col1, col2 = st.columns([0.1, 0.9])
                        with col1:
                            st.checkbox(
                                "",
                                key=f"kb_{kb['kb_name']}",
                                value=kb['kb_name'] in st.session_state.selected_resources['kbs'],
                                on_change=lambda k=kb['kb_name']: toggle_resource('kbs', k)
                            )
                        with col2:
                            st.write(f"🔹 {kb['alias']}")
                
                # Database
                db_name = f"{source_name.lower().replace('-', '_').replace(' ', '_')}_db"
                st.write("🗄️ **Database**")
                col1, col2 = st.columns([0.1, 0.9])
                with col1:
                    st.checkbox(
                        "",
                        key=f"db_{db_name}",
                        value=db_name in st.session_state.selected_resources['dbs'],
                        on_change=lambda d=db_name: toggle_resource('dbs', d)
                    )
                with col2:
                    st.write(f"`{db_name}`")
    
        # Update Agent Button
        st.divider()
        st.write("### 🤖 Agent Skills")
        if st.session_state.selected_resources['kbs'] or st.session_state.selected_resources['dbs']:
            selected_kbs = len(st.session_state.selected_resources['kbs'])
            selected_dbs = len(st.session_state.selected_resources['dbs'])
            st.write(f"Selected: {selected_kbs} KBs, {selected_dbs} DBs")
            
            if st.button("Update Agent Skills", type="primary"):
                with st.spinner("Updating agent skills..."):
                    result = create_agent_skills(
                        st.session_state.selected_resources['kbs'],
                        st.session_state.selected_resources['dbs']
                    )
                    
                    if result['status'] == "success":
                        # Show warnings first if any
                        if result.get("warnings"):
                            st.warning("\n".join(result["warnings"]))
                            
                        # Show any non-blocking errors
                        if result.get("errors"):
                            st.error("\n".join(result["errors"]))
                            
                        # Show success message
                        msg = "✅ Agent updated successfully!\n\n"
                        if result.get("skills_added"):
                            msg += f"Added: {', '.join(result['skills_added'])}\n"
                        if result.get("skills_removed"):
                            msg += f"Removed: {', '.join(result['skills_removed'])}"
                        st.success(msg)
                        st.session_state.agent_ready = True
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        if result.get('details'):
                            error_msg += "\n\n" + "\n".join(result['details'])
                        st.error(f"❌ Failed to update agent: {error_msg}")
        else:
            st.info("Select resources above to update agent skills")
    
    # Sidebar bottom buttons
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Refresh"):
            st.session_state.kbs = []
            get_kbs()
            st.rerun()
    with col2:
        if st.button("➕ Create"):
            st.session_state.current_step = 1
            st.session_state._switch_to_manage = True
            st.rerun()

# --- Main Content Area ---
tab1, tab2 = st.tabs(["💬 Chat", "🔧 Manage Resources"])

# --- Chat Tab ---
with tab1:
    if st.session_state.get('agent_ready', False):
        chat_container = st.container()
        
        # Display chat messages
        with chat_container:
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.write(message["content"])
                    if message.get("context"):
                        with st.expander("View sources", expanded=False):
                            st.json(message["context"])
        
        # Sticky chat input at bottom
        with st.container():
            st.divider()
            if prompt := st.chat_input("Ask a question about your data...", key="chat_input"):
                with st.chat_message("user"):
                    st.write(prompt)
                    st.session_state.messages.append({"role": "user", "content": prompt})
                
                with st.chat_message("assistant"):
                    with st.spinner('Thinking...'):
                        response = ask_agent(prompt)
                        if "error" in response:
                            st.error(response["error"])
                        else:
                            st.write(response["response"])
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": response["response"],
                                "context": response.get("context")
                            })
                            if response.get("context"):
                                with st.expander("View sources", expanded=False):
                                    st.json(response["context"])
    else:
        st.info("⚠️ Please select and update agent skills in the sidebar first")

# --- Manage Resources Tab ---
with tab2:
    st.write("## 🔧 Create New Resources")
    
    # Progress steps
    steps = ["Select Connector", "Configure Source", "Select Data", "Create Resources"]
    current_step = st.session_state.current_step
    
    # Progress bar
    progress_cols = st.columns(len(steps))
    for idx, step in enumerate(steps, 1):
        with progress_cols[idx-1]:
            if idx < current_step:
                st.markdown(f"✅ **{step}**")
            elif idx == current_step:
                st.markdown(f"🔵 **{step}**")
            else:
                st.markdown(f"⚪ {step}")
    
    st.divider()
    
    # Create New Source section
    with st.expander("Create New Source", expanded=current_step == 1):
        # Step 1: Choose Connector
        if current_step == 1:
            source_options = get_sources()
            selected_source = st.selectbox("Select a Connector:", source_options)
            
            col1, col2 = st.columns(2)
            with col1:
                user_source_name = st.text_input(
                    "Custom Name",
                    value=selected_source.replace('source-', '') if selected_source else '',
                    help="Give this source a friendly name"
                )
            with col2:
                source_description = st.text_area(
                    "Description",
                    help="Add a helpful description"
                )
            
            if st.button("Next →", type="primary"):
                if selected_source and user_source_name:
                    # Store values in session state
                    st.session_state.source_name = selected_source
                    st.session_state.user_source_name = user_source_name
                    st.session_state.source_description = source_description
                    st.session_state.source_selected = True
                    st.session_state.current_step = 2
                    st.rerun()
                else:
                    st.error("Please fill in all required fields")
        
        # Step 2: Configure Source
        elif current_step == 2:
            spec = get_source_spec(st.session_state.source_name)
            st.info(f"Configuring {st.session_state.user_source_name}")
            
            if isinstance(spec, dict):
                with st.form("source_config"):
                    config_values = {}
                    for field, val in spec.get("connectionSpecification", {}).get("properties", {}).items():
                        field_type = val.get("type")
                        field_label = val.get("title", field)
                        
                        # Enhanced field rendering with better layout
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            if field_type == "string":
                                config_values[field] = st.text_input(
                                    field_label,
                                    value=val.get("default", ""),
                                    type="password" if "password" in field.lower() else "default",
                                    help=val.get("description")
                                )
                            elif field_type == "integer":
                                config_values[field] = st.number_input(field_label, value=val.get("default", 0),help=val.get("description"))
                            elif field_type == "boolean":
                                config_values[field] = st.checkbox(field_label, value=val.get("default", False), help=val.get("description"))
                            elif field_type == "array":
                                config_values[field] = st.text_area(field_label, help=val.get('description')).split(",")
                            elif field_type == "object":
                                config_values[field] = st.text_area(field_label, value=str(val.get("default", {}), help=val.get("description")))
                        with col2:
                            if val.get("description"):
                                st.info(val.get("description"))
                    
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        back = st.form_submit_button("← Back")
                    with col2:
                        next = st.form_submit_button("Test & Continue →")
                    
                    if back:
                        st.session_state.current_step = 1
                        st.rerun()
                    if next:
                        with st.spinner("Testing connection..."):
                            response = configure_source(st.session_state.source_name, config_values)
                            if "message" in response:
                                st.success("✅ Connection successful!")
                                st.session_state.source_configured = True
                                st.session_state.config_values = config_values
                                st.session_state.current_step = 3
                                streams = get_streams()
                                if streams:
                                    st.session_state.available_streams = streams
                                    st.session_state.streams_fetched = True
                                    st.rerun()
                            else:
                                st.error(f"❌ Connection failed: {response.get('error', 'Unknown error')}")
        
        # Step 3: Select Streams & Fields
        elif current_step == 3:
            if st.session_state.streams_fetched:
                st.subheader("Select Data Streams")
                selected_streams = st.multiselect(
                    "Select Data Streams",
                    st.session_state.available_streams,
                    key="stream_selector"
                )
                
                if selected_streams:
                    if st.button("Load Fields"):
                        st.session_state.selected_streams = selected_streams or []
                        select_streams(selected_streams)
                        records = fetch_schema()
                        if "records" in records:
                            st.session_state.schema_records = records["records"]
                            st.rerun()
                
                # Add null check before iteration
                if st.session_state.selected_streams and "schema_records" in st.session_state:
                    st.subheader("Configure Fields")
                    metadata_columns = {}
                    content_columns = {}
                    
                    for stream in st.session_state.selected_streams:
                        st.write(f"### Stream: {stream}")
                        stream_container = st.container()
                        with stream_container:
                            col1, col2 = st.columns(2)
                            with col1:
                                metadata_fields = st.multiselect(
                                    "Metadata Fields",
                                    list(st.session_state.schema_records[stream].keys()),
                                    help="Fields to use for filtering and organization",
                                    key=f"metadata_{stream}"
                                )
                            with col2:
                                content_fields = st.multiselect(
                                    "Content Fields",
                                    list(st.session_state.schema_records[stream].keys()),
                                    help="Fields containing the main content",
                                    key=f"content_{stream}"
                                )
                            metadata_columns[stream] = metadata_fields
                            content_columns[stream] = content_fields
                        st.divider()
                    
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        if st.button("← Back"):
                            st.session_state.current_step = 2
                            st.rerun()
                    with col2:
                        if st.button("Create Resources →", type="primary"):
                            with st.spinner("Creating AI resources..."):
                                result = create_kb(
                                    source_name=st.session_state.source_name,
                                    user_source_name=st.session_state.user_source_name,
                                    source_description=st.session_state.source_description,
                                    streams=st.session_state.selected_streams,
                                    metadata_columns=metadata_columns,
                                    content_columns=content_columns
                                )
                                
                                if "message" in result:
                                    st.success(f"✅ Resources created successfully!\n{ result['message']}")
                                    # Clear source-related session state
                                    st.session_state.source_name = None
                                    st.session_state.user_source_name = None
                                    st.session_state.source_description = None
                                    st.session_state.config_values = None
                                    st.session_state.selected_streams = None
                                    st.session_state.schema_records = None
                                    st.session_state.available_streams = None
                                    st.session_state.kbs = []
                                    get_kbs()
                                    st.session_state.current_step = 4
                                    st.rerun()
                                else:
                                    st.error(f"❌ Creation failed: {result.get('error', 'Unknown error')}")
    
    # View Resources (simplified view without skill selection)
    st.write("### Existing Resources")
    if sources:
        for source_name, details in sources.items():
            with st.expander(f"{details['status']} {source_name}", expanded=True):
                st.caption(f"Created: {details['created_at']}")
                if details['description']:
                    st.info(details['description'])
                
                # Display KBs
                if details['kbs']:
                    st.write("📚 **Knowledge Bases**")
                    for kb in details['kbs']:
                        col1, col2 = st.columns([0.8, 0.2])
                        with col1:
                            st.write(f"∟ {kb['alias']}")
                        with col2:
                            if st.button("ℹ️", key=f"info_{kb['kb_name']}"):
                                st.info(f"""
                                - KB Name: `{kb['kb_name']}`
                                - Stream: {kb['alias']}
                                - Created: {kb['created_at']}
                                """)
                
                # Display DB - Use normalize_db_name for consistency
                db_name = f"{source_name.lower().replace('-', '_').replace(' ', '_')}_db"
                st.write("🗄️ **Database**")
                st.write(f"`{db_name}`")

# Toggle resource selection function
def toggle_resource(resource_type, resource_name):
    resources = st.session_state.selected_resources[resource_type]
    if resource_name in resources:
        resources.remove(resource_name)
    else:
        resources.append(resource_name)
    st.session_state.selected_resources[resource_type] = resources
