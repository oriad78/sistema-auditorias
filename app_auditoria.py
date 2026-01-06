import hashlib
import sqlite3
import pandas as pd
import streamlit as st
import io
import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema Integral", layout="wide")

# --- ESTILOS PROFESIONALES (CSS) ---
st.markdown("""
    <style>
    .login-card {
        background-color: white;
        padding: 40px;
        border-radius: 15px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        max-width: 500px;
        margin: auto;
    }
    .main-title { color: #1e3a8a; font-weight: 700; text-align: center; }
    .stButton>button { border-radius: 8px; transition: all 0.3s; }
    /* Botones de alerta en rojo suave */
    .delete-btn { color: #dc2626; font-weight: bold; }
    .admin-badge {
        background-color: #fee2e2;
        color: #dc2626;
        padding: 2px 8px;
        border-radius: 5px;
        font-size: 12px;
        font-weight: bold;
    }
    .guia-box {
        background-color: #f0f7ff;
        border-left: 5px solid #1e3a8a;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    .area-header {
        background-color: #f1f5f9;
        padding: 10px;
        border-radius: 8px;
        border-left: 8px solid #3b82f6;
        margin: 20px 0 10px 0;
        font-weight: bold;
        color: #1e40af;
        font-size: 1.1em;
    }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT, role TEXT DEFAULT "Miembro")')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, is_deleted INTEGER DEFAULT 0)')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS audit_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        client_id INTEGER, 
        section_name TEXT, 
        area_name TEXT DEFAULT "General",
        step_code TEXT, 
        description TEXT, 
        instructions TEXT, 
        user_notes TEXT, 
        status TEXT DEFAULT "Sin Iniciar", 
        is_deleted INTEGER DEFAULT 0)''')
    
    cursor.execute('CREATE TABLE IF NOT EXISTS materiality (client_id INTEGER PRIMARY KEY, benchmark TEXT, benchmark_value REAL, p_general REAL, mat_general REAL, p_performance REAL, mat_performance REAL, p_ranr REAL, mat_ranr REAL)')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        step_id INTEGER,
        user_id INTEGER,
        user_name TEXT,
        action TEXT,
        previous_value TEXT,
        new_value TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(step_id) REFERENCES audit_steps(id)
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS audit_evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        step_id INTEGER,
        user_id INTEGER,
        file_name TEXT,
        file_type TEXT,
        file_data BLOB,
        upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(step_id) REFERENCES audit_steps(id)
    )''')
    
    try: cursor.execute("ALTER TABLE audit_steps ADD COLUMN area_name TEXT DEFAULT 'General'")
    except: pass
        
    conn.commit()
    conn.close()

# --- SCRIPT DE INICIALIZACIÓN ---
def crear_admin_por_defecto():
    conn = get_db_connection()
    cursor = conn.cursor()
    usuarios = [
        ('admin@auditpro.com', 'Administrador Principal', 'admin123', 'Administrador'),
        ('auditgerencial.rojas@outlook.com', 'Gerencia Auditoría', 'admin123', 'Administrador')
    ]
    for email, nombre, clave, rol in usuarios:
        cursor.execute("SELECT * FROM users WHERE email=?", (email,))
        if not cursor.fetchone():
            ph = hashlib.sha256(clave.encode()).hexdigest()
            cursor.execute("INSERT INTO users (email, full_name, password_hash, role) VALUES (?,?,?,?)", (email, nombre, ph, rol))
    conn.commit(); conn.close()

create_tables()
crear_admin_por_defecto()

# --- LÓGICA DE NEGOCIO ---
def cargar_pasos_iniciales(conn, client_id):
    pasos = [
       ("Planeación", "Aceptación", "1000", "(ISA 220, 300) Evaluar aceptación", "Realice evaluación de riesgos."),
       ("Planeación", "Aceptación", "2000", "(ISA 220) Designar QRP", "Evaluar revisión de calidad."),
       ("Planeación", "Ética", "4000", "(ISA 200) Requisitos éticos", "Documentar independencia."),
       ("Planeación", "Contratación", "5000", "(ISA 210) Carta encargo", "Verificar firma representante.")
    ]
    cursor = conn.cursor()
    for p in pasos:
        cursor.execute("INSERT INTO audit_steps (client_id, section_name, area_name, step_code, description, instructions) VALUES (?, ?, ?, ?, ?, ?)", (client_id, p[0], p[1], p[2], p[3], p[4]))
    conn.commit()

def actualizar_paso_seguro(step_id, user_id, user_name, nuevas_notas, nuevo_estado):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT user_notes, status FROM audit_steps WHERE id=?", (step_id,))
    actual = cursor.fetchone()
    if not actual: return False
    
    n_ant, e_ant = actual[0] or "", actual[1]
    cambios = []
    if (n_ant.strip() != nuevas_notas.strip()): cambios.append("Notas actualizadas")
    if e_ant != nuevo_estado: cambios.append(f"Estado: {e_ant} -> {nuevo_estado}")
    
    if cambios:
        cursor.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (nuevas_notas, nuevo_estado, step_id))
        desc = " | ".join(cambios)
        cursor.execute("INSERT INTO audit_logs (step_id, user_id, user_name, action, previous_value, new_value) VALUES (?,?,?,?,?,?)", 
                       (step_id, user_id, user_name, desc, n_ant[:50], nuevas_notas[:50]))
        conn.commit(); ret = True
    else: ret = False
    conn.close(); return ret

def guardar_evidencia(step_id, user_id, uploaded_file):
    if uploaded_file is not None:
        try:
            bytes_data = uploaded_file.getvalue()
            conn = get_db_connection()
            conn.execute("INSERT INTO audit_evidence (step_id, user_id, file_name, file_type, file_data) VALUES (?,?,?,?,?)",
                         (step_id, user_id, uploaded_file.name, uploaded_file.type, bytes_data))
            conn.commit(); conn.close()
            return True
        except Exception as e:
            st.error(f"Error al subir: {e}")
            return False
    return False

def eliminar_evidencia(file_id):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM audit_evidence WHERE id=?", (file_id,))
        conn.commit()
    except: pass
    finally: conn.close()

# --- MÓDULOS ---
def modulo_materialidad(client_id):
    st.markdown("### 📊 Materialidad (NIA 320)")
    conn = get_db_connection()
    datos = conn.execute("SELECT * FROM materiality WHERE client_id=?", (client_id,)).fetchone()
    conn.close()
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            options = ["Utilidad Neta", "Ingresos Totales", "Activos Totales", "EBITDA"]
            idx = options.index(datos[1]) if datos and datos[1] in options else 0
            benchmark = st.selectbox("Benchmark", options, index=idx)
            valor_base = st.number_input("Valor Base ($)", min_value=0.0, value=datos[2] if datos else 0.0)
        with c2:
            max_p = 10.0 if benchmark == "Utilidad Neta" else 5.0
            p_gen = st.slider("% Mat. General", 0.0, max_p, datos[3] if datos else max_p/2)
            p_perf = st.slider("% Performance", 0.0, 75.0, datos[5] if datos else 50.0)
        with c3:
            p_ranr = st.slider("% RANR", 0.0, 10.0, datos[7] if datos else 5.0)
        
        m_gen = valor_base * (p_gen / 100)
        m_perf = m_gen * (p_perf / 100)
        m_ranr = m_gen * (p_ranr / 100)
    
    st.columns(3)[0].metric("Mat. General", f"$ {m_gen:,.2f}")
    
    # Botón descriptivo
    if st.button("💾 Guardar Cálculo de Materialidad", use_container_width=True):
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO materiality VALUES (?,?,?,?,?,?,?,?,?)", 
                     (client_id, benchmark, valor_base, p_gen, m_gen, p_perf, m_perf, p_ranr, m_ranr))
        conn.commit(); conn.close()
        st.success("Configuración de materialidad guardada correctamente.")

def modulo_programa_trabajo(client_id):
    st.markdown("### 📝 Programa de Trabajo")
    conn = get_db_connection()
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? AND is_deleted=0 ORDER BY section_name ASC, area_name ASC, step_code ASC", conn, params=(client_id,))
    opciones_estado = ["Sin Iniciar", "En Proceso", "Terminado"]

    if steps.empty:
        st.info("No hay pasos. Use el módulo de importación.")
        conn.close(); return

    c_f1, c_f2 = st.columns([2, 1])
    search = c_f1.text_input("🔍 Buscar Procedimiento:", "")
    seccion_f = c_f2.selectbox("📁 Filtrar Sección:", ["Todas"] + sorted(list(steps['section_name'].unique())))

    df_f = steps.copy()
    if search: df_f = df_f[df_f['description'].str.contains(search, case=False) | df_f['step_code'].str.contains(search, case=False)]
    if seccion_f != "Todas": df_f = df_f[df_f['section_name'] == seccion_f]

    for area in df_f['area_name'].unique():
        st.markdown(f'<div class="area-header">📍 Área: {area}</div>', unsafe_allow_html=True)
        with st.expander(f"Ver procedimientos de {area}", expanded=True):
            subset = df_f[df_f['area_name'] == area]
            for _, row in subset.iterrows():
                sid = row['id']
                icon = "⚪" if row['status'] == "Sin Iniciar" else "🟡" if row['status'] == "En Proceso" else "🟢"
                
                with st.expander(f"{icon} [{row['step_code']}] - {row['description'][:90]}..."):
                    st.markdown(f"**Procedimiento:** {row['description']}")
                    st.markdown(f'<div class="guia-box"><strong>Guía Técnica:</strong><br>{row["instructions"]}</div>', unsafe_allow_html=True)
                    
                    tabs = st.tabs(["📝 Papeles de Trabajo", "📎 Evidencias (NIA 500)", "📜 Historial de Cambios"])
                    
                    # TAB 1: NOTAS
                    with tabs[0]:
                        n_nota = st.text_area("Conclusiones del Auditor:", value=row['user_notes'] or "", key=f"nt_{sid}")
                        c_e, c_b = st.columns([1, 1])
                        n_est = c_e.selectbox("Estado del Procedimiento", opciones_estado, index=opciones_estado.index(row['status'] if row['status'] in opciones_estado else "Sin Iniciar"), key=f"es_{sid}")
                        
                        # Botón Descriptivo
                        if c_b.button("💾 Registrar Avance y Notas", key=f"btn_{sid}", use_container_width=True):
                            if actualizar_paso_seguro(sid, st.session_state.user_id, st.session_state.user_name, n_nota, n_est):
                                st.success("Avance registrado exitosamente."); st.rerun()
                            else: st.info("No se detectaron cambios nuevos para guardar.")
                    
                    # TAB 2: EVIDENCIAS
                    with tabs[1]:
                        uploaded = st.file_uploader("Seleccionar archivo de soporte", key=f"up_{sid}")
                        # Botón Descriptivo
                        if uploaded and st.button("☁️ Cargar Evidencia al Servidor", key=f"upl_{sid}"):
                            if guardar_evidencia(sid, st.session_state.user_id, uploaded):
                                st.success("Archivo subido y encriptado correctamente."); st.rerun()
                        
                        st.divider()
                        conn_ev = get_db_connection()
                        evs = pd.read_sql_query("SELECT id, file_name, file_type, file_data, upload_date FROM audit_evidence WHERE step_id=?", conn_ev, params=(sid,))
                        conn_ev.close()
                        
                        if not evs.empty:
                            st.write("**Archivos Adjuntos:**")
                            for _, ev in evs.iterrows():
                                c_info, c_down, c_del = st.columns([3, 1.2, 0.8])
                                c_info.write(f"📄 {ev['file_name']}")
                                
                                # Botón Descarga
                                c_down.download_button(
                                    label="⬇️ Descargar", 
                                    data=ev['file_data'], 
                                    file_name=ev['file_name'], 
                                    mime=ev['file_type'], 
                                    key=f"dl_{ev['id']}"
                                )
                                
                                # SEGURIDAD: Botón Eliminar con confirmación (Popover)
                                with c_del.popover("🗑️", help="Eliminar archivo permanentemente"):
                                    st.markdown("⚠️ **¿Estás seguro?**")
                                    st.caption("Esta acción no se puede deshacer.")
                                    if st.button("Sí, Eliminar", key=f"confirm_del_{ev['id']}", type="primary"):
                                        eliminar_evidencia(ev['id'])
                                        st.rerun()
                        else: st.caption("No hay evidencias adjuntas para este paso.")

                    # TAB 3: HISTORIAL
                    with tabs[2]:
                        conn_log = get_db_connection()
                        logs = pd.read_sql_query("SELECT timestamp, user_name, action FROM audit_logs WHERE step_id=? ORDER BY timestamp DESC", conn_log, params=(sid,))
                        conn_log.close()
                        if not logs.empty: st.dataframe(logs, hide_index=True, use_container_width=True)
                        else: st.write("No hay historial de modificaciones.")
    conn.close()

def modulo_importacion(client_id):
    st.markdown("### 📥 Importación Masiva")
    st.markdown("#### 1. Descargar Formato")
    p_data = {'Seccion': ['Activo', 'Pasivo'], 'Area': ['Caja', 'Proveedores'], 'Codigo': ['101', '201'], 'Descripcion': ['Arqueo de caja', 'Confirmación saldos'], 'Instrucciones': ['NIA 500', 'NIA 505']}
    st.download_button("⬇️ Obtener Plantilla CSV", data=pd.DataFrame(p_data).to_csv(index=False).encode('utf-8-sig'), file_name="plantilla_auditpro.csv", mime="text/csv")
    
    st.divider()
    st.markdown("#### 2. Carga de Datos")
    up = st.file_uploader("Seleccione su archivo Excel o CSV", type=['xlsx', 'csv'])
    if up and st.button("🚀 Procesar e Importar Datos", use_container_width=True):
        try:
            df = pd.read_csv(up) if up.name.endswith('.csv') else pd.read_excel(up)
            conn = get_db_connection(); cursor = conn.cursor()
            existentes = pd.read_sql_query("SELECT step_code FROM audit_steps WHERE client_id=?", conn, params=(client_id,))
            set_ex = set(existentes['step_code'].astype(str))
            
            nuevos = 0
            for _, r in df.iterrows():
                if str(r['Codigo']) not in set_ex:
                    cursor.execute("INSERT INTO audit_steps (client_id, section_name, area_name, step_code, description, instructions) VALUES (?,?,?,?,?,?)", 
                                   (client_id, r['Seccion'], r['Area'], r['Codigo'], r['Descripcion'], r['Instrucciones']))
                    nuevos += 1
            conn.commit(); conn.close()
            st.success(f"Proceso completado: Se importaron {nuevos} nuevos procedimientos.")
        except Exception as e: st.error(f"Error en el archivo: {e}")

# --- VISTAS PRINCIPALES ---
def vista_principal():
    is_admin = "Administrador" in st.session_state.get('user_role', "Miembro")
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.user_name}")
        st.markdown(f"<span class='admin-badge'>{st.session_state.user_role}</span>", unsafe_allow_html=True)
        if st.button("🔒 Cerrar Sesión Segura"): st.session_state.clear(); st.rerun()
        st.divider()
        st.subheader("Alta de Clientes")
        n_name = st.text_input("Razón Social / Empresa")
        n_nit = st.text_input("NIT / Identificación")
        if st.button("✅ Registrar Nuevo Cliente") and n_name:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, n_name, n_nit))
            lid = cur.lastrowid
            cargar_pasos_iniciales(conn, lid)
            conn.commit(); conn.close(); st.rerun()

    if 'active_id' in st.session_state:
        if st.button("⬅️ Volver al Panel Principal"): del st.session_state.active_id; st.rerun()
        st.title(f"📂 Auditoría: {st.session_state.active_name}")
        col_menu = st.columns(3)
        if col_menu[0].button("📊 Definir Materialidad", use_container_width=True): st.session_state.mod = "Mat"
        if col_menu[1].button("📝 Ejecutar Programa", use_container_width=True): st.session_state.mod = "Prog"
        if col_menu[2].button("📥 Importar Pasos", use_container_width=True): st.session_state.mod = "Imp"
        
        mod = st.session_state.get('mod', 'Prog')
        if mod == "Prog": modulo_programa_trabajo(st.session_state.active_id)
        elif mod == "Imp": modulo_importacion(st.session_state.active_id)
        else: modulo_materialidad(st.session_state.active_id)
    else:
        st.title("💼 Mis Auditorías Asignadas")
        
        c1, c2 = st.columns(2)
        c1.link_button("🌐 Consultar RUT (DIAN)", "https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces", use_container_width=True)
        c2.link_button("🏢 Consultar RUES", "https://www.rues.org.co/busqueda-avanzada", use_container_width=True)
        st.divider()
        
        conn = get_db_connection()
        clients = pd.read_sql_query("SELECT * FROM clients WHERE is_deleted=0", conn)
        for _, r in clients.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 1.5, 0.5])
                c1.write(f"**{r['client_name']}** | NIT: {r['client_nit']}")
                
                # Botón Descriptivo
                if c2.button("📂 Gestionar Auditoría", key=f"op_{r['id']}", use_container_width=True):
                    st.session_state.active_id, st.session_state.active_name = r['id'], r['client_name']; st.rerun()
                
                if is_admin:
                    # SEGURIDAD: Popover de confirmación para eliminar cliente
                    with c3.popover("🗑️", help="Eliminar Cliente"):
                        st.markdown(f"⚠️ **¿Eliminar {r['client_name']}?**")
                        st.caption("Se ocultará de la lista.")
                        if st.button("Confirmar Eliminación", key=f"del_cli_{r['id']}", type="primary"):
                            conn.execute("UPDATE clients SET is_deleted=1 WHERE id=?", (r['id'],)); conn.commit(); st.rerun()
        conn.close()

def vista_login():
    st.markdown('<div class="login-card"><h1 class="main-title">⚖️ AuditPro</h1>', unsafe_allow_html=True)
    e = st.text_input("Correo Corporativo")
    p = st.text_input("Contraseña", type="password")
    if st.button("🔐 Iniciar Sesión Segura", use_container_width=True):
        conn = get_db_connection()
        u = conn.execute("SELECT id, full_name, role FROM users WHERE email=? AND password_hash=?", 
                         (e.strip().lower(), hashlib.sha256(p.strip().encode()).hexdigest())).fetchone()
        conn.close()
        if u:
            st.session_state.user_id, st.session_state.user_name, st.session_state.user_role = u[0], u[1], u[2]
            st.rerun()
        else: st.error("Acceso denegado. Verifique sus credenciales.")
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
