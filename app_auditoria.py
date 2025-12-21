import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import re
import json
from datetime import datetime
import os

# Configuración de la página
st.set_page_config(
    page_title="Sistema de Gestión de Auditorías",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estructura de base de datos
class AuditDatabase:
    def __init__(self):
        self.conn = sqlite3.connect('audit_management.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                client_name TEXT NOT NULL,
                audit_year INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS folder_structure (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                parent_id INTEGER,
                folder_name TEXT NOT NULL,
                folder_type TEXT,
                folder_order INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients (id),
                FOREIGN KEY (parent_id) REFERENCES folder_structure (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER,
                step_order TEXT,
                publication_date DATE,
                step_description TEXT,
                data_type TEXT,
                attachments TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (folder_id) REFERENCES folder_structure (id)
            )
        ''')
        
        self.conn.commit()

# Hash y validación de contraseña
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def validate_password(password):
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"
    if not re.search(r'[A-Z]', password):
        return False, "La contraseña debe contener al menos una letra mayúscula"
    if not re.search(r'[a-z]', password):
        return False, "La contraseña debe contener al menos una letra minúscula"
    if not re.search(r'[0-9]', password):
        return False, "La contraseña debe contener al menos un número"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "La contraseña debe contener al menos un carácter especial"
    return True, "Contraseña válida"

# Login
def login_system():
    st.sidebar.title("🔐 Inicio de Sesión")
    
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
        st.session_state.user_email = None
    
    if st.session_state.user_id is None:
        tab1, tab2 = st.sidebar.tabs(["Iniciar Sesión", "Registrarse"])
        
        with tab1:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Contraseña", type="password", key="login_password")
            
            if st.button("Iniciar Sesión"):
                db = AuditDatabase()
                cursor = db.conn.cursor()
                cursor.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,))
                result = cursor.fetchone()
                
                if result and result[1] == hash_password(password):
                    st.session_state.user_id = result[0]
                    st.session_state.user_email = email
                    st.sidebar.success("¡Inicio de sesión exitoso!")
                    st.rerun()
                else:
                    st.sidebar.error("Email o contraseña incorrectos")
        
        with tab2:
            new_email = st.text_input("Email", key="register_email")
            full_name = st.text_input("Nombre Completo", key="register_name")
            new_password = st.text_input("Contraseña", type="password", key="register_password")
            confirm_password = st.text_input("Confirmar Contraseña", type="password", key="confirm_password")
            
            if st.button("Registrarse"):
                if new_password != confirm_password:
                    st.sidebar.error("Las contraseñas no coinciden")
                else:
                    is_valid, message = validate_password(new_password)
                    if not is_valid:
                        st.sidebar.error(message)
                    else:
                        db = AuditDatabase()
                        cursor = db.conn.cursor()
                        try:
                            cursor.execute("INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)", (new_email, hash_password(new_password), full_name))
                            db.conn.commit()
                            st.sidebar.success("¡Registro exitoso! Ahora puedes iniciar sesión.")
                        except sqlite3.IntegrityError:
                            st.sidebar.error("Este email ya está registrado")
    else:
        st.sidebar.success(f"Bienvenido, {st.session_state.user_email}")
        if st.sidebar.button("Cerrar Sesión"):
            st.session_state.user_id = None
            st.session_state.user_email = None
            st.rerun()

# Estructura base
def get_base_structure():
    return {
        "Planeación": { ... },  # (tu estructura completa, la mantengo igual)
        "Ejecución": { ... }
    }  # (la misma que tenías, no la repito aquí por espacio, pero cópiala tal cual)

# Crear carpetas
def create_folder_structure(db, client_id, parent_id, structure, folder_type):
    for folder_name, subfolders in structure.items():
        cursor = db.conn.cursor()
        cursor.execute("INSERT INTO folder_structure (client_id, parent_id, folder_name, folder_type) VALUES (?, ?, ?, ?)", (client_id, parent_id, folder_name, folder_type))
        folder_id = cursor.lastrowid
        
        if subfolders:
            next_type = {'main': 'stage', 'stage': 'sub1', 'sub1': 'sub2', 'sub2': 'sub3', 'sub3': 'sub4'}.get(folder_type, 'sub4')
            create_folder_structure(db, client_id, folder_id, subfolders, next_type)
        
        db.conn.commit()

# Gestión de clientes (LA PARTE IMPORTANTE)
def client_management():
    st.title("👥 Gestión de Clientes de Auditoría")
    
    db = AuditDatabase()
    
    # Crear nuevo encargo
    with st.expander("➕ Crear Nuevo Encargo/Cliente", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            client_name = st.text_input("Nombre del Cliente", key="input_client_name")
        with col2:
            audit_year = st.number_input("Año de Auditoría", min_value=2000, max_value=2100, value=datetime.now().year, key="input_audit_year")
        
        if st.button("Crear Encargo", key="crear_encargo_btn"):
            if not client_name.strip():
                st.error("Por favor ingresa un nombre para el cliente")
            else:
                cursor = db.conn.cursor()
                cursor.execute("INSERT INTO clients (user_id, client_name, audit_year) VALUES (?, ?, ?)", (st.session_state.user_id, client_name.strip(), audit_year))
                client_id = cursor.lastrowid
                
                create_folder_structure(db, client_id, None, get_base_structure(), 'main')
                
                db.conn.commit()
                
                st.success(f"Encargo '{client_name.strip()}' creado exitosamente para el año {audit_year}")
                st.balloons()
                
                st.session_state.input_client_name = ""
                st.session_state.input_audit_year = datetime.now().year
                st.rerun()
    
    # Lista de encargos
    st.subheader("📋 Encargos Existentes")
    
    cursor = db.conn.cursor()
    cursor.execute("SELECT id, client_name, audit_year, created_at FROM clients WHERE user_id = ? ORDER BY audit_year DESC, client_name", (st.session_state.user_id,))
    clients = cursor.fetchall()
    
    if clients:
        for client_id, name, year, created in clients:
            with st.expander(f"🏢 {name} - Año {year}"):
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.write(f"**Creado:** {created}")
                with col2:
                    if st.button("📂 Abrir Estructura", key=f"open_{client_id}"):
                        st.session_state.current_client = client_id
                        st.session_state.current_client_name = name
                        st.rerun()
                with col3:
                    if st.button("🗑️ Eliminar", key=f"delete_{client_id}"):
                        cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))
                        db.conn.commit()
                        st.success(f"Encargo '{name}' eliminado")
                        st.rerun()
    else:
        st.info("No hay encargos creados. Usa el formulario arriba para crear tu primer encargo.")
    
        # ================================================
    # ELIMINAR VARIOS ENCARGOS CON CASILLAS (SIEMPRE VISIBLE)
    # ================================================
    st.markdown("---")
    st.markdown("<h3 style='text-align: center; color: red;'>🗑️ ELIMINAR VARIOS ENCARGOS A LA VEZ</h3>", unsafe_allow_html=True)
    st.markdown("**Marca las casillas de los encargos que quieres borrar y confirma abajo**")
    
    # Usamos el mismo cursor de la lista anterior para no crear nuevos db
    cursor.execute(
        "SELECT id, client_name, audit_year FROM clients WHERE user_id = ? ORDER BY audit_year DESC, client_name",
        (st.session_state.user_id,)
    )
    all_clients = cursor.fetchall()
    
    if all_clients:
        selected_ids = []
        cols = st.columns(3)  # Para que las casillas se vean en columnas bonitas
        for i, (client_id, name, year) in enumerate(all_clients):
            with cols[i % 3]:
                if st.checkbox(f"{name} - Año {year}", key=f"del_multi_{client_id}"):
                    selected_ids.append(client_id)
        
        if selected_ids:
            st.markdown(f"**⚠️ Has seleccionado {len(selected_ids)} encargo(s) para eliminar**")
            
            if st.checkbox("**Sí, confirmo que quiero eliminarlos permanentemente (no se puede deshacer)**", key="confirm_multi_delete"):
                if st.button("🗑️ ELIMINAR LOS ENCARGOS SELECCIONADOS", type="primary", key="btn_multi_delete"):
                    placeholders = ','.join(['?'] * len(selected_ids))
                    
                    cursor.execute(f"""
                        DELETE FROM audit_steps 
                        WHERE folder_id IN (
                            SELECT id FROM folder_structure 
                            WHERE client_id IN ({placeholders})
                        )
                    """, selected_ids)
                    
                    cursor.execute(f"DELETE FROM folder_structure WHERE client_id IN ({placeholders})", selected_ids)
                    
                    cursor.execute(f"DELETE FROM clients WHERE id IN ({placeholders})", selected_ids)
                    
                    db.conn.commit()
                    
                    st.success(f"¡Eliminados {len(selected_ids)} encargos con éxito!")
                    st.balloons()
                    st.rerun()
        else:
            st.info("No has seleccionado ningún encargo para eliminar.")
    else:
        st.info("No hay encargos para eliminar.")
    
    st.markdown("---")
    
# Las funciones navigate_folder_structure, show_audit_steps y main_app quedan igual que en tu código original

def navigate_folder_structure(db, folder_id=None, client_id=None, level=0):
    # (igual que antes)
    pass  # copia tu código original aquí

def show_audit_steps(db, folder_id):
    # (igual que antes)
    pass  # copia tu código original aquí

def main_app():
    login_system()
    
    if st.session_state.user_id is None:
        st.title("Sistema de Gestión de Auditorías")
        st.markdown("Bienvenido... (tu texto)")
        return
    
    menu = st.sidebar.selectbox("Navegación", ["Gestión de Clientes", "Estructura de Auditoría", "Reportes"])
    
    if menu == "Gestión de Clientes":
        client_management()
    # ... resto igual

if __name__ == "__main__":
    main_app()

