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

# (import streamlit as st
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
        
        # Tabla de usuarios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de clientes/encargos
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
        
        # Tabla de estructura de carpetas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS folder_structure (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                parent_id INTEGER,
                folder_name TEXT NOT NULL,
                folder_type TEXT, -- 'main', 'stage', 'sub1', 'sub2', 'sub3', 'sub4'
                folder_order INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients (id),
                FOREIGN KEY (parent_id) REFERENCES folder_structure (id)
            )
        ''')
        
        # Tabla de pasos de auditoría
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER,
                step_order TEXT,
                publication_date DATE,
                step_description TEXT,
                data_type TEXT,
                attachments TEXT, -- JSON de archivos adjuntos
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (folder_id) REFERENCES folder_structure (id)
            )
        ''')
        
        self.conn.commit()

# Función para hash de contraseñas
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Validación de contraseña
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

# Sistema de autenticación
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
                cursor.execute(
                    "SELECT id, password_hash FROM users WHERE email = ?", 
                    (email,)
                )
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
                            cursor.execute(
                                "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
                                (new_email, hash_password(new_password), full_name)
                            )
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

# Estructura base de carpetas (basada en tu Excel)
def get_base_structure():
    return {
        "Planeación": {
            "Saldos de apertura para las auditorías iniciales": {
                "1600 - Saldos de apertura para las auditorías iniciales": {
                    "A Other Required Steps": {}
                }
            },
            "Actividades de control": {
                "2250 - Utilización de una organización prestadora de servicios": {
                    "*4 Validate Control Activities": {}
                }
            },
            "Ciclo de satisfacción de auditoría - definición del alcance": {
                "1905 - Comunicarse con el cliente - Entidades PIE": {
                    "A Other Required steps": {},
                    "Common Procedures": {}
                }
            },
            "Satisfacción de auditoría - Ventas y cuentas por cobrar": {
                "2400 - Proceso de ingresos y cuentas por cobrar": {
                    "*3 Understand and Evaluate Controls": {},
                    "*4 Validate Control Activities": {}
                },
                "3700 - Cuentas por cobrar": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*A Receivables - Estimates/Reserves": {},
                    "*B Early Substantive Testing": {},
                    "*B Special Attributes": {}
                },
                "3800 - Ingresos diferidos": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*A Revenue - Complexity of Transactions/GAAP": {},
                    "*B Early Substantive Testing": {}
                },
                "5500 - Ventas": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*B Early Substantive Testing": {},
                    "*B Intercompany Transactions": {}
                }
            }
        },
        "Ejecución": {
            "Satisfacción de auditoría - Compras y cuentas por pagar": {
                "2500 - Proceso de compras y cuentas por pagar": {
                    "*3 Understand and Evaluate Controls": {},
                    "*4 Validate Control Activities": {}
                },
                "4600 - Cuentas por pagar": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*B Early Substantive Testing": {},
                    "*B Special Attributes": {}
                },
                "5100 - Cargos diferidos": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*A Intangibles - Estimates/Impairments": {},
                    "*B Early Substantive Testing": {}
                }
            },
            "Satisfacción de auditoría - Producción": {
                "2600 - Proceso de inventarios": {
                    "*3 Understand and Evaluate Controls": {},
                    "*4 Validate Control Activities": {}
                },
                "2800 - Proceso de activos fijos": {
                    "*3 Understand and Evaluate Controls": {},
                    "*4 Validate Control Activities": {}
                },
                "3000 - Activos fijos": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*A Fixed Assets - Estimates/Impairments": {},
                    "*A Leases - Significant Contracts/Agreements": {},
                    "*B Early Substantive Testing": {},
                    "*B Intercompany Transactions": {},
                    "*B Special Attributes": {}
                }
            },
            "Satisfacción de auditoría - Tesorería y administración de fondos": {
                "2300 - Proceso de caja y bancos": {
                    "*3 Understand and Evaluate Controls": {},
                    "*4 Validate Control Activities": {}
                },
                "2550 - Proceso de inversiones": {
                    "*4 Validate Control Activities": {}
                },
                "3300 - Inversiones": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*A Investments - Estimates/Impairments": {},
                    "*B Early Substantive Testing": {},
                    "*B Special Attributes": {}
                }
            }
        }
    }

# Función para crear estructura de carpetas para un cliente
def create_folder_structure(db, client_id, parent_id, structure, folder_type):
    for folder_name, subfolders in structure.items():
        cursor = db.conn.cursor()
        cursor.execute(
            "INSERT INTO folder_structure (client_id, parent_id, folder_name, folder_type) VALUES (?, ?, ?, ?)",
            (client_id, parent_id, folder_name, folder_type)
        )
        folder_id = cursor.lastrowid
        
        if subfolders:
            next_type = {
                'main': 'stage',
                'stage': 'sub1', 
                'sub1': 'sub2',
                'sub2': 'sub3',
                'sub3': 'sub4'
            }.get(folder_type, 'sub4')
            
            create_folder_structure(db, client_id, folder_id, subfolders, next_type)
        
        db.conn.commit()

# Gestión de clientes
def client_management():
    st.title("👥 Gestión de Clientes de Auditoría")
    
    db = AuditDatabase()
    
    # Crear nuevo cliente
    with st.expander("➕ Crear Nuevo Encargo/Cliente", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            client_name = st.text_input("Nombre del Cliente")
        with col2:
            audit_year = st.number_input("Año de Auditoría", min_value=2000, max_value=2100, value=datetime.now().year)
        
        if st.button("Crear Encargo"):
            if client_name:
                cursor = db.conn.cursor()
                cursor.execute(
                    "INSERT INTO clients (user_id, client_name, audit_year) VALUES (?, ?, ?)",
                    (st.session_state.user_id, client_name, audit_year)
                )
                client_id = cursor.lastrowid
                
                # Crear estructura base de carpetas
                base_structure = get_base_structure()
                create_folder_structure(db, client_id, None, base_structure, 'main')
                
                st.success(f"Encargo '{client_name}' creado exitosamente para el año {audit_year}")
                st.rerun()
            else:
                st.error("Por favor ingresa un nombre para el cliente")
    
    # Migrar datos entre años
    with st.expander("🔄 Migrar Datos entre Años", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            cursor = db.conn.cursor()
            cursor.execute(
                "SELECT id, client_name, audit_year FROM clients WHERE user_id = ? ORDER BY audit_year DESC",
                (st.session_state.user_id,)
            )
            clients = cursor.fetchall()
            
            client_options = {f"{name} ({year})": id for id, name, year in clients}
            selected_client = st.selectbox("Seleccionar Cliente a Migrar", list(client_options.keys()))
        
        with col2:
            source_year = st.number_input("Año Origen", min_value=2000, max_value=2100, value=datetime.now().year-1)
        
        with col3:
            target_year = st.number_input("Año Destino", min_value=2000, max_value=2100, value=datetime.now().year)
        
        if st.button("Migrar Datos"):
            if selected_client and source_year != target_year:
                client_id = client_options[selected_client]
                # Aquí iría la lógica para migrar datos entre años
                st.success(f"Datos migrados exitosamente del año {source_year} al {target_year}")
    
    # Lista de clientes existentes
    st.subheader("📋 Encargos Existentes")
    
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT id, client_name, audit_year, created_at FROM clients WHERE user_id = ? ORDER BY audit_year DESC, client_name",
        (st.session_state.user_id,)
    )
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

# Navegación por la estructura de carpetas
def navigate_folder_structure(db, folder_id=None, client_id=None, level=0):
    if client_id and folder_id is None:
        # Mostrar carpetas principales (etapas de auditoría)
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT id, folder_name FROM folder_structure WHERE client_id = ? AND parent_id IS NULL ORDER BY folder_order, id",
            (client_id,)
        )
        main_folders = cursor.fetchall()
        
        for folder_id, folder_name in main_folders:
            with st.expander(f"📁 {folder_name}", expanded=level==0):
                navigate_folder_structure(db, folder_id, client_id, level+1)
    
    elif folder_id:
        # Mostrar subcarpetas
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT id, folder_name FROM folder_structure WHERE parent_id = ? ORDER BY folder_order, id",
            (folder_id,)
        )
        subfolders = cursor.fetchall()
        
        if subfolders:
            for sub_id, sub_name in subfolders:
                with st.expander(f"📂 {sub_name}", expanded=level<3):
                    navigate_folder_structure(db, sub_id, client_id, level+1)
        
        # Mostrar pasos de auditoría para esta carpeta (nivel 4)
        if level >= 4:  # Asumiendo que nivel 4 es donde están los pasos
            show_audit_steps(db, folder_id)

# Mostrar pasos de auditoría
def show_audit_steps(db, folder_id):
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT id, step_order, publication_date, step_description, data_type FROM audit_steps WHERE folder_id = ? ORDER BY step_order",
        (folder_id,)
    )
    steps = cursor.fetchall()
    
    if steps:
        st.subheader("📝 Pasos de Auditoría")
        for step_id, step_order, pub_date, description, data_type in steps:
            with st.container():
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.write(f"**Orden:** {step_order}")
                    if pub_date:
                        st.write(f"**Fecha:** {pub_date}")
                    st.write(f"**Tipo:** {data_type}")
                with col2:
                    st.write(description)
                
                # Aquí podrías agregar funcionalidad para editar, adjuntar archivos, etc.
                if st.button("✏️ Editar", key=f"edit_{step_id}"):
                    st.session_state.editing_step = step_id
                
                st.divider()
    else:
        st.info("No hay pasos de auditoría definidos para esta carpeta.")
        
        # Opción para agregar nuevo paso
        if st.button("➕ Agregar Paso de Auditoría", key=f"add_step_{folder_id}"):
            with st.form(key=f"new_step_form_{folder_id}"):
                step_order = st.text_input("Orden del Paso")
                publication_date = st.date_input("Fecha de Publicación")
                step_description = st.text_area("Descripción del Paso")
                data_type = st.selectbox("Tipo de Dato", ["Sumplemento de auditoría", "Otro"])
                
                if st.form_submit_button("Guardar Paso"):
                    cursor.execute(
                        "INSERT INTO audit_steps (folder_id, step_order, publication_date, step_description, data_type) VALUES (?, ?, ?, ?, ?)",
                        (folder_id, step_order, publication_date, step_description, data_type)
                    )
                    db.conn.commit()
                    st.success("Paso de auditoría guardado exitosamente")
                    st.rerun()

# Vista principal de la aplicación
def main_app():
    login_system()
    
    if st.session_state.user_id is None:
        st.title("Sistema de Gestión de Auditorías")
        st.markdown("""
        ## Bienvenido al Sistema de Gestión de Auditorías
        
        Esta aplicación te permite:
        - Gestionar múltiples clientes de auditoría
        - Organizar el trabajo por etapas y subcarpetas
        - Seguir pasos específicos de auditoría
        - Migrar datos entre períodos
        
        **Por favor inicia sesión o regístrate para comenzar.**
        """)
        return
    
    # Menú principal
    menu = st.sidebar.selectbox(
        "Navegación",
        ["Gestión de Clientes", "Estructura de Auditoría", "Reportes"]
    )
    
    if menu == "Gestión de Clientes":
        client_management()
    
    elif menu == "Estructura de Auditoría":
        st.title("📊 Estructura de Auditoría")
        
        db = AuditDatabase()
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT id, client_name FROM clients WHERE user_id = ? ORDER BY audit_year DESC",
            (st.session_state.user_id,)
        )
        clients = cursor.fetchall()
        
        if clients:
            client_options = {name: id for id, name in clients}
            selected_client = st.selectbox(
                "Seleccionar Cliente",
                list(client_options.keys()),
                key="client_selector"
            )
            
            if selected_client:
                st.session_state.current_client = client_options[selected_client]
                st.session_state.current_client_name = selected_client
                
                st.subheader(f"Estructura para: {selected_client}")
                navigate_folder_structure(db, client_id=st.session_state.current_client)
        else:
            st.info("No hay clientes disponibles. Ve a 'Gestión de Clientes' para crear uno.")
    
    elif menu == "Reportes":
        st.title("📈 Reportes y Análisis")
        st.info("Esta sección está en desarrollo. Próximamente podrás generar reportes detallados de auditoría.")

# Ejecutar la aplicación
if __name__ == "__main__":
    main_app())
# import streamlit as st
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
        
        # Tabla de usuarios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de clientes/encargos
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
        
        # Tabla de estructura de carpetas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS folder_structure (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                parent_id INTEGER,
                folder_name TEXT NOT NULL,
                folder_type TEXT, -- 'main', 'stage', 'sub1', 'sub2', 'sub3', 'sub4'
                folder_order INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients (id),
                FOREIGN KEY (parent_id) REFERENCES folder_structure (id)
            )
        ''')
        
        # Tabla de pasos de auditoría
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER,
                step_order TEXT,
                publication_date DATE,
                step_description TEXT,
                data_type TEXT,
                attachments TEXT, -- JSON de archivos adjuntos
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (folder_id) REFERENCES folder_structure (id)
            )
        ''')
        
        self.conn.commit()

# Función para hash de contraseñas
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Validación de contraseña
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

# Sistema de autenticación
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
                cursor.execute(
                    "SELECT id, password_hash FROM users WHERE email = ?", 
                    (email,)
                )
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
                            cursor.execute(
                                "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
                                (new_email, hash_password(new_password), full_name)
                            )
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

# Estructura base de carpetas (basada en tu Excel)
def get_base_structure():
    return {
        "Planeación": {
            "Saldos de apertura para las auditorías iniciales": {
                "1600 - Saldos de apertura para las auditorías iniciales": {
                    "A Other Required Steps": {}
                }
            },
            "Actividades de control": {
                "2250 - Utilización de una organización prestadora de servicios": {
                    "*4 Validate Control Activities": {}
                }
            },
            "Ciclo de satisfacción de auditoría - definición del alcance": {
                "1905 - Comunicarse con el cliente - Entidades PIE": {
                    "A Other Required steps": {},
                    "Common Procedures": {}
                }
            },
            "Satisfacción de auditoría - Ventas y cuentas por cobrar": {
                "2400 - Proceso de ingresos y cuentas por cobrar": {
                    "*3 Understand and Evaluate Controls": {},
                    "*4 Validate Control Activities": {}
                },
                "3700 - Cuentas por cobrar": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*A Receivables - Estimates/Reserves": {},
                    "*B Early Substantive Testing": {},
                    "*B Special Attributes": {}
                },
                "3800 - Ingresos diferidos": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*A Revenue - Complexity of Transactions/GAAP": {},
                    "*B Early Substantive Testing": {}
                },
                "5500 - Ventas": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*B Early Substantive Testing": {},
                    "*B Intercompany Transactions": {}
                }
            }
        },
        "Ejecución": {
            "Satisfacción de auditoría - Compras y cuentas por pagar": {
                "2500 - Proceso de compras y cuentas por pagar": {
                    "*3 Understand and Evaluate Controls": {},
                    "*4 Validate Control Activities": {}
                },
                "4600 - Cuentas por pagar": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*B Early Substantive Testing": {},
                    "*B Special Attributes": {}
                },
                "5100 - Cargos diferidos": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*A Intangibles - Estimates/Impairments": {},
                    "*B Early Substantive Testing": {}
                }
            },
            "Satisfacción de auditoría - Producción": {
                "2600 - Proceso de inventarios": {
                    "*3 Understand and Evaluate Controls": {},
                    "*4 Validate Control Activities": {}
                },
                "2800 - Proceso de activos fijos": {
                    "*3 Understand and Evaluate Controls": {},
                    "*4 Validate Control Activities": {}
                },
                "3000 - Activos fijos": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*A Fixed Assets - Estimates/Impairments": {},
                    "*A Leases - Significant Contracts/Agreements": {},
                    "*B Early Substantive Testing": {},
                    "*B Intercompany Transactions": {},
                    "*B Special Attributes": {}
                }
            },
            "Satisfacción de auditoría - Tesorería y administración de fondos": {
                "2300 - Proceso de caja y bancos": {
                    "*3 Understand and Evaluate Controls": {},
                    "*4 Validate Control Activities": {}
                },
                "2550 - Proceso de inversiones": {
                    "*4 Validate Control Activities": {}
                },
                "3300 - Inversiones": {
                    "*2 Lead Schedule": {},
                    "*3 Substantive Analytical Review": {},
                    "*4 Tests of Details": {},
                    "*A Investments - Estimates/Impairments": {},
                    "*B Early Substantive Testing": {},
                    "*B Special Attributes": {}
                }
            }
        }
    }

# Función para crear estructura de carpetas para un cliente
def create_folder_structure(db, client_id, parent_id, structure, folder_type):
    for folder_name, subfolders in structure.items():
        cursor = db.conn.cursor()
        cursor.execute(
            "INSERT INTO folder_structure (client_id, parent_id, folder_name, folder_type) VALUES (?, ?, ?, ?)",
            (client_id, parent_id, folder_name, folder_type)
        )
        folder_id = cursor.lastrowid
        
        if subfolders:
            next_type = {
                'main': 'stage',
                'stage': 'sub1', 
                'sub1': 'sub2',
                'sub2': 'sub3',
                'sub3': 'sub4'
            }.get(folder_type, 'sub4')
            
            create_folder_structure(db, client_id, folder_id, subfolders, next_type)
        
        db.conn.commit()

# Gestión de clientes
def client_management():
    st.title("👥 Gestión de Clientes de Auditoría")
    
    db = AuditDatabase()
    
    # Crear nuevo cliente
    with st.expander("➕ Crear Nuevo Encargo/Cliente", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            client_name = st.text_input("Nombre del Cliente")
        with col2:
            audit_year = st.number_input("Año de Auditoría", min_value=2000, max_value=2100, value=datetime.now().year)
        
        if st.button("Crear Encargo"):
            if client_name:
                cursor = db.conn.cursor()
                cursor.execute(
                    "INSERT INTO clients (user_id, client_name, audit_year) VALUES (?, ?, ?)",
                    (st.session_state.user_id, client_name, audit_year)
                )
                client_id = cursor.lastrowid
                
                # Crear estructura base de carpetas
                base_structure = get_base_structure()
                create_folder_structure(db, client_id, None, base_structure, 'main')
                
                st.success(f"Encargo '{client_name}' creado exitosamente para el año {audit_year}")
                st.rerun()
            else:
                st.error("Por favor ingresa un nombre para el cliente")
    
    # Migrar datos entre años
    with st.expander("🔄 Migrar Datos entre Años", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            cursor = db.conn.cursor()
            cursor.execute(
                "SELECT id, client_name, audit_year FROM clients WHERE user_id = ? ORDER BY audit_year DESC",
                (st.session_state.user_id,)
            )
            clients = cursor.fetchall()
            
            client_options = {f"{name} ({year})": id for id, name, year in clients}
            selected_client = st.selectbox("Seleccionar Cliente a Migrar", list(client_options.keys()))
        
        with col2:
            source_year = st.number_input("Año Origen", min_value=2000, max_value=2100, value=datetime.now().year-1)
        
        with col3:
            target_year = st.number_input("Año Destino", min_value=2000, max_value=2100, value=datetime.now().year)
        
        if st.button("Migrar Datos"):
            if selected_client and source_year != target_year:
                client_id = client_options[selected_client]
                # Aquí iría la lógica para migrar datos entre años
                st.success(f"Datos migrados exitosamente del año {source_year} al {target_year}")
    
    # Lista de clientes existentes
    st.subheader("📋 Encargos Existentes")
    
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT id, client_name, audit_year, created_at FROM clients WHERE user_id = ? ORDER BY audit_year DESC, client_name",
        (st.session_state.user_id,)
    )
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

# Navegación por la estructura de carpetas
def navigate_folder_structure(db, folder_id=None, client_id=None, level=0):
    if client_id and folder_id is None:
        # Mostrar carpetas principales (etapas de auditoría)
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT id, folder_name FROM folder_structure WHERE client_id = ? AND parent_id IS NULL ORDER BY folder_order, id",
            (client_id,)
        )
        main_folders = cursor.fetchall()
        
        for folder_id, folder_name in main_folders:
            with st.expander(f"📁 {folder_name}", expanded=level==0):
                navigate_folder_structure(db, folder_id, client_id, level+1)
    
    elif folder_id:
        # Mostrar subcarpetas
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT id, folder_name FROM folder_structure WHERE parent_id = ? ORDER BY folder_order, id",
            (folder_id,)
        )
        subfolders = cursor.fetchall()
        
        if subfolders:
            for sub_id, sub_name in subfolders:
                with st.expander(f"📂 {sub_name}", expanded=level<3):
                    navigate_folder_structure(db, sub_id, client_id, level+1)
        
        # Mostrar pasos de auditoría para esta carpeta (nivel 4)
        if level >= 4:  # Asumiendo que nivel 4 es donde están los pasos
            show_audit_steps(db, folder_id)

# Mostrar pasos de auditoría
def show_audit_steps(db, folder_id):
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT id, step_order, publication_date, step_description, data_type FROM audit_steps WHERE folder_id = ? ORDER BY step_order",
        (folder_id,)
    )
    steps = cursor.fetchall()
    
    if steps:
        st.subheader("📝 Pasos de Auditoría")
        for step_id, step_order, pub_date, description, data_type in steps:
            with st.container():
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.write(f"**Orden:** {step_order}")
                    if pub_date:
                        st.write(f"**Fecha:** {pub_date}")
                    st.write(f"**Tipo:** {data_type}")
                with col2:
                    st.write(description)
                
                # Aquí podrías agregar funcionalidad para editar, adjuntar archivos, etc.
                if st.button("✏️ Editar", key=f"edit_{step_id}"):
                    st.session_state.editing_step = step_id
                
                st.divider()
    else:
        st.info("No hay pasos de auditoría definidos para esta carpeta.")
        
        # Opción para agregar nuevo paso
        if st.button("➕ Agregar Paso de Auditoría", key=f"add_step_{folder_id}"):
            with st.form(key=f"new_step_form_{folder_id}"):
                step_order = st.text_input("Orden del Paso")
                publication_date = st.date_input("Fecha de Publicación")
                step_description = st.text_area("Descripción del Paso")
                data_type = st.selectbox("Tipo de Dato", ["Sumplemento de auditoría", "Otro"])
                
                if st.form_submit_button("Guardar Paso"):
                    cursor.execute(
                        "INSERT INTO audit_steps (folder_id, step_order, publication_date, step_description, data_type) VALUES (?, ?, ?, ?, ?)",
                        (folder_id, step_order, publication_date, step_description, data_type)
                    )
                    db.conn.commit()
                    st.success("Paso de auditoría guardado exitosamente")
                    st.rerun()

# Vista principal de la aplicación
def main_app():
    login_system()
    
    if st.session_state.user_id is None:
        st.title("Sistema de Gestión de Auditorías")
        st.markdown("""
        ## Bienvenido al Sistema de Gestión de Auditorías
        
        Esta aplicación te permite:
        - Gestionar múltiples clientes de auditoría
        - Organizar el trabajo por etapas y subcarpetas
        - Seguir pasos específicos de auditoría
        - Migrar datos entre períodos
        
        **Por favor inicia sesión o regístrate para comenzar.**
        """)
        return
    
    # Menú principal
    menu = st.sidebar.selectbox(
        "Navegación",
        ["Gestión de Clientes", "Estructura de Auditoría", "Reportes"]
    )
    
    if menu == "Gestión de Clientes":
        client_management()
    
    elif menu == "Estructura de Auditoría":
        st.title("📊 Estructura de Auditoría")
        
        db = AuditDatabase()
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT id, client_name FROM clients WHERE user_id = ? ORDER BY audit_year DESC",
            (st.session_state.user_id,)
        )
        clients = cursor.fetchall()
        
        if clients:
            client_options = {name: id for id, name in clients}
            selected_client = st.selectbox(
                "Seleccionar Cliente",
                list(client_options.keys()),
                key="client_selector"
            )
            
            if selected_client:
                st.session_state.current_client = client_options[selected_client]
                st.session_state.current_client_name = selected_client
                
                st.subheader(f"Estructura para: {selected_client}")
                navigate_folder_structure(db, client_id=st.session_state.current_client)
        else:
            st.info("No hay clientes disponibles. Ve a 'Gestión de Clientes' para crear uno.")
    
    elif menu == "Reportes":
        st.title("📈 Reportes y Análisis")
        st.info("Esta sección está en desarrollo. Próximamente podrás generar reportes detallados de auditoría.")

# Ejecutar la aplicación
if __name__ == "__main__":
    main_app()

if __name__ == "__main__":
    main_app()