import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import re
from datetime import datetime

# --- CONFIGURACIÓN Y ESTILOS ---
st.set_page_config(
    page_title="AuditPro | Gestión de Auditoría",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inyectar CSS para mejorar la estética
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; }
    .client-card {
        padding: 1.5rem;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        background-color: white;
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CLASE DE BASE DE DATOS ---
class AuditDatabase:
    def __init__(self):
        self.conn = sqlite3.connect('audit_management.db', check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        # Usuarios
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        # Clientes
        cursor.execute('''CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            client_name TEXT NOT NULL,
            audit_year INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE)''')
        # Estructura de carpetas
        cursor.execute('''CREATE TABLE IF NOT EXISTS folder_structure (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            parent_id INTEGER,
            folder_name TEXT NOT NULL,
            folder_type TEXT,
            FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
            FOREIGN KEY (parent_id) REFERENCES folder_structure (id) ON DELETE CASCADE)''')
        # Pasos de auditoría
        cursor.execute('''CREATE TABLE IF NOT EXISTS audit_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_id INTEGER,
            step_description TEXT,
            status TEXT DEFAULT 'Pendiente',
            FOREIGN KEY (folder_id) REFERENCES folder_structure (id) ON DELETE CASCADE)''')
        self.conn.commit()

# --- FUNCIONES DE UTILIDAD ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_base_structure():
    return {
        "01. Planeación": {"Memorándum": {}, "Riesgos": {}, "Cronograma": {}},
        "02. Ejecución": {"Activos": {}, "Pasivos": {}, "Patrimonio": {}},
        "03. Finalización": {"Informe": {}, "Carta de Gerencia": {}}
    }

def create_folder_recursive(db, client_id, parent_id, structure):
    cursor = db.conn.cursor()
    for name, sub in structure.items():
        cursor.execute("INSERT INTO folder_structure (client_id, parent_id, folder_name) VALUES (?, ?, ?)",
                       (client_id, parent_id, name))
        folder_id = cursor.lastrowid
        if sub:
            create_folder_recursive(db, client_id, folder_id, sub)
    db.conn.commit()

# --- COMPONENTES DE INTERFAZ ---
def login_system():
    with st.sidebar:
        st.title("🔐 Acceso")
        if 'user_id' not in st.session_state:
            st.session_state.user_id = None
        
        if st.session_state.user_id is None:
            mode = st.radio("Acción", ["Ingresar", "Registrarse"])
            email = st.text_input("Email")
            password = st.text_input("Contraseña", type="password")
            
            if mode == "Ingresar" and st.button("Login"):
                db = AuditDatabase()
                cursor = db.conn.cursor()
                cursor.execute("SELECT id, password_hash, full_name FROM users WHERE email = ?", (email,))
                user = cursor.fetchone()
                if user and user[1] == hash_password(password):
                    st.session_state.user_id = user[0]
                    st.session_state.user_name = user[2]
                    st.rerun()
                else:
                    st.error("Credenciales inválidas")
            
            elif mode == "Registrarse" and st.button("Crear Cuenta"):
                # Lógica simplificada de registro para el ejemplo
                db = AuditDatabase()
                try:
                    db.conn.cursor().execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", 
                                           (email, hash_password(password)))
                    db.conn.commit()
                    st.success("Cuenta creada. Por favor ingrese.")
                except: st.error("El usuario ya existe.")
        else:
            st.write(f"Conectado como: **{st.session_state.user_name}**")
            if st.button("Cerrar Sesión"):
                st.session_state.user_id = None
                st.rerun()

def client_management():
    st.title("💼 Panel de Control de Auditoría")
    db = AuditDatabase()
    
    # 1. CREACIÓN DE ENCARGO
    with st.expander("✨ Crear Nuevo Encargo", expanded=False):
        c1, c2 = st.columns(2)
        with c1: 
            new_name = st.text_input("Nombre de la Entidad")
        with c2: 
            new_year = st.number_input("Ejercicio Fiscal", value=2024)
        
        if st.button("Inicializar Auditoría", type="primary"):
            if new_name:
                cursor = db.conn.cursor()
                cursor.execute("INSERT INTO clients (user_id, client_name, audit_year) VALUES (?, ?, ?)",
                             (st.session_state.user_id, new_name, new_year))
                client_id = cursor.lastrowid
                create_folder_recursive(db, client_id, None, get_base_structure())
                st.success(f"Estructura creada para {new_name}")
                st.rerun()

    # 2. LISTADO Y ACCIONES
    st.subheader("📋 Auditorías Activas")
    cursor = db.conn.cursor()
    cursor.execute("SELECT id, client_name, audit_year, created_at FROM clients WHERE user_id = ?", (st.session_state.user_id,))
    clients = cursor.fetchall()

    if not clients:
        st.info("No hay encargos registrados actualmente.")
        return

    # Mostrar como tarjetas profesionales
    for cid, name, year, date in clients:
        with st.container(border=True):
            col_info, col_btn1, col_btn2 = st.columns([3, 1, 1])
            with col_info:
                st.markdown(f"**{name}**")
                st.caption(f"Año: {year} | Creado: {date[:10]}")
            with col_btn1:
                if st.button(f"📂 Abrir", key=f"open_{cid}"):
                    st.session_state.current_client = cid
                    st.info(f"Cargando {name}...")
            with col_btn2:
                if st.button(f"🗑️", key=f"del_{cid}", help="Borrado rápido"):
                    cursor.execute("DELETE FROM clients WHERE id = ?", (cid,))
                    db.conn.commit()
                    st.rerun()

    # 3. BORRADO MASIVO (TU PETICIÓN)
    st.markdown("---")
    with st.expander("🛠️ Gestión Masiva de Datos", expanded=False):
        st.warning("Selecciona múltiples encargos para eliminarlos permanentemente.")
        to_delete = []
        cols = st.columns(4)
        for i, (cid, name, year, _) in enumerate(clients):
            with cols[i % 4]:
                if st.checkbox(f"{name} ({year})", key=f"bulk_{cid}"):
                    to_delete.append(cid)
        
        if to_delete:
            if st.button(f"🔥 Eliminar {len(to_delete)} seleccionados", type="primary"):
                # Usamos una transacción segura
                placeholders = ','.join(['?'] * len(to_delete))
                try:
                    cursor.execute(f"DELETE FROM clients WHERE id IN ({placeholders})", to_delete)
                    db.conn.commit()
                    st.toast("Encargos eliminados correctamente")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

# --- APP PRINCIPAL ---
def main():
    login_system()
    
    if st.session_state.user_id:
        menu = st.sidebar.selectbox("Navegación", ["Clientes", "Reportes", "Configuración"])
        if menu == "Clientes":
            client_management()
        else:
            st.title(menu)
            st.info("Sección en desarrollo...")
    else:
        st.title("🚀 Sistema de Auditoría Digital")
        st.write("Por favor, inicie sesión en el panel lateral para comenzar.")

if __name__ == "__main__":
    main()
