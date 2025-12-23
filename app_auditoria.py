import hashlib
import sqlite3
import pandas as pd
import streamlit as st

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AuditPro - Sistema Integral", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .step-header { 
        background-color: #f8f9fa;
        padding: 10px;
        border-radius: 5px;
        border-left: 10px solid #d32f2f;
        color: #333; 
        font-weight: bold; 
        font-size: 16px; 
        margin-bottom: 5px; 
    }
    .instruction-box { 
        background-color: #e3f2fd; 
        border-left: 5px solid #2196f3; 
        padding: 12px; 
        margin-bottom: 15px; 
        border-radius: 5px;
        font-size: 13px;
        color: #0d47a1;
    }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
def get_db_connection():
    return sqlite3.connect('audit_management.db', timeout=10, check_same_thread=False)

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, full_name TEXT, password_hash TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, client_name TEXT, client_nit TEXT, tipo_trabajo TEXT, estado TEXT DEFAULT "Pendiente")')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_steps (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, section_name TEXT, step_code TEXT, description TEXT, instructions TEXT, user_notes TEXT, status TEXT DEFAULT "Sin Iniciar")')
    cursor.execute('CREATE TABLE IF NOT EXISTS materiality (client_id INTEGER PRIMARY KEY, benchmark TEXT, benchmark_value REAL, p_general REAL, mat_general REAL, p_performance REAL, mat_performance REAL, p_ranr REAL, mat_ranr REAL)')
    
    # Reparación para clientes antiguos: poner "Sin Iniciar" si el estado es nulo
    cursor.execute("UPDATE audit_steps SET status = 'Sin Iniciar' WHERE status IS NULL OR status = ''")
    
    conn.commit()
    conn.close()

create_tables()

# --- MÓDULO: MATERIALIDAD ---
def modulo_materialidad(client_id):
    st.markdown("### 📊 Determinación de la Materialidad")
    
    conn = get_db_connection()
    datos = conn.execute("SELECT * FROM materiality WHERE client_id=?", (client_id,)).fetchone()
    conn.close()

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            benchmark = st.selectbox("Base (Benchmark)", ["Utilidad Neta", "Ingresos Totales", "Activos Totales", "EBITDA"],
                index=0 if not datos else ["Utilidad Neta", "Ingresos Totales", "Activos Totales", "EBITDA"].index(datos[1]))
            valor_base = st.number_input("Valor Base ($)", min_value=0.0, value=datos[2] if datos else 0.0)
        with c2:
            max_p = 10.0 if benchmark == "Utilidad Neta" else 5.0
            p_gen = st.slider("% Mat. General", 0.0, max_p, datos[3] if datos else max_p/2)
            p_perf = st.slider("% Performance", 0.0, 75.0, datos[5] if datos else 50.0)
        with c3:
            p_ranr = st.slider("% RANR (Ajustes)", 0.0, 10.0, datos[7] if datos else 5.0)

        m_gen = valor_base * (p_gen / 100)
        m_perf = m_gen * (p_perf / 100)
        m_ranr = m_gen * (p_ranr / 100)

    res1, res2, res3 = st.columns(3)
    res1.metric("Mat. General", f"$ {m_gen:,.2f}")
    res2.metric("Mat. Desempeño", f"$ {m_perf:,.2f}")
    res3.metric("Límite RANR", f"$ {m_ranr:,.2f}")

    if st.button("💾 Guardar Materialidad"):
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO materiality VALUES (?,?,?,?,?,?,?,?,?)", (client_id, benchmark, valor_base, p_gen, m_gen, p_perf, m_perf, p_ranr, m_ranr))
        conn.commit(); conn.close(); st.success("Guardado")

# --- MÓDULO: PROGRAMA DE TRABAJO (CON SEMÁFOROS CORREGIDOS) ---
def modulo_programa_trabajo(client_id):
    st.markdown("### 📝 Programa de Trabajo y Ejecución")
    
    conn = get_db_connection()
    steps = pd.read_sql_query("SELECT * FROM audit_steps WHERE client_id=? ORDER BY section_name, step_code", conn, params=(client_id,))
    
    iconos = {"Sin Iniciar": "🔴", "En Proceso": "🟡", "Terminado": "🟢"}
    colores_borde = {"Sin Iniciar": "#d32f2f", "En Proceso": "#fbc02d", "Terminado": "#388e3c"}

    for seccion in steps['section_name'].unique():
        st.subheader(f"📁 {seccion}")
        pasos_seccion = steps[steps['section_name'] == seccion]
        
        for _, row in pasos_seccion.iterrows():
            sid = row['id']
            estado = row['status'] if row['status'] in iconos else "Sin Iniciar"
            color = colores_borde.get(estado, "#d32f2f")
            
            # Título con borde dinámico según el color del estado
            st.markdown(f"""
                <div style="border-left: 10px solid {color}; background-color: #f8f9fa; padding: 10px; border-radius: 5px; font-weight: bold; margin-bottom: 5px;">
                    {iconos[estado]} {row['step_code']} - {row['description']}
                </div>
            """, unsafe_allow_html=True)
            
            # Guía NIA
            if row['instructions']:
                st.markdown(f"<div class='instruction-box'><b>💡 Guía Técnica:</b> {row['instructions']}</div>", unsafe_allow_html=True)
            
            c_nota, c_estado = st.columns([3, 1])
            with c_nota:
                nueva_nota = st.text_area("Evidencia/Notas", value=row['user_notes'] or "", key=f"nt_{sid}", height=100)
            with c_estado:
                nuevo_est = st.selectbox("Estado", ["Sin Iniciar", "En Proceso", "Terminado"], 
                                         index=["Sin Iniciar", "En Proceso", "Terminado"].index(estado), key=f"es_{sid}")
                if st.button("Guardar Paso", key=f"bt_{sid}"):
                    conn.execute("UPDATE audit_steps SET user_notes=?, status=? WHERE id=?", (nueva_nota, nuevo_est, sid))
                    conn.commit()
                    st.rerun()
            st.divider()
    conn.close()

# --- VISTA: EXPEDIENTE ---
def vista_expediente(client_id, client_name):
    c1, c2 = st.columns([5, 1])
    c1.title(f"📂 {client_name}")
    if c2.button("⬅️ Volver"):
        if 'active_id' in st.session_state: del st.session_state.active_id
        st.rerun()

    if 'current_module' not in st.session_state: st.session_state.current_module = "Materialidad"

    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    if m1.button("📊 Materialidad", use_container_width=True): st.session_state.current_module = "Materialidad"
    if m2.button("📝 Programa de Trabajo", use_container_width=True): st.session_state.current_module = "Programa"
    if m3.button("📥 Exportar", use_container_width=True): st.session_state.current_module = "Exportar"
    st.markdown("---")

    if st.session_state.current_module == "Materialidad":
        modulo_materialidad(client_id)
    elif st.session_state.current_module == "Programa":
        modulo_programa_trabajo(client_id)
    else:
        st.info("Módulo de exportación en construcción...")

# --- VISTA PRINCIPAL ---
def vista_principal():
    with st.sidebar:
        st.write(f"Auditor: **{st.session_state.user_name}**")
        if st.button("Cerrar Sesión"): st.session_state.clear(); st.rerun()
        st.divider()
        st.subheader("Crear Nuevo Encargo")
        name = st.text_input("Empresa"); nit = st.text_input("NIT")
        if st.button("Registrar Auditoría"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO clients (user_id, client_name, client_nit) VALUES (?,?,?)", (st.session_state.user_id, name, nit))
            cid = cur.lastrowid
            # Plantilla con guías NIA
            pasos = [
                ("100 Planeación", "1010", "Aceptación y Continuidad", "Evaluar la integridad del cliente y si el equipo tiene la competencia (NIA 220)."),
                ("100 Planeación", "1020", "Carta de Encargo", "Asegurar que los términos de la auditoría estén por escrito (NIA 210)."),
                ("200 Ejecución", "2010", "Arqueo de Caja", "Realizar conteo físico de efectivo y valores en poder del cajero."),
            ]
            for sec, cod, desc, ins in pasos:
                conn.execute("INSERT INTO audit_steps (client_id, section_name, step_code, description, instructions, status) VALUES (?,?,?,?,?,?)", (cid, sec, cod, desc, ins, "Sin Iniciar"))
            conn.commit(); conn.close(); st.rerun()

    if 'active_id' in st.session_state:
        vista_expediente(st.session_state.active_id, st.session_state.active_name)
    else:
        st.title("💼 Mis Auditorías")
        conn = get_db_connection()
        clients = pd.read_sql_query("SELECT * FROM clients WHERE user_id=?", conn, params=(st.session_state.user_id,))
        for _, r in clients.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.write(f"**{r['client_name']}** (NIT: {r['client_nit']})")
                if c2.button("Abrir Expediente", key=f"op_{r['id']}"):
                    st.session_state.active_id, st.session_state.active_name = r['id'], r['client_name']; st.rerun()
        conn.close()

# --- LOGIN ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()
def vista_login():
    st.title("⚖️ AuditPro")
    e, p = st.text_input("Correo"), st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        conn = get_db_connection()
        u = conn.execute("SELECT id, full_name FROM users WHERE email=? AND password_hash=?", (e, hash_pass(p))).fetchone()
        conn.close()
        if u: st.session_state.user_id, st.session_state.user_name = u[0], u[1]; st.rerun()
        else: st.error("Error")
    if st.button("Registrar"):
        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (email, full_name, password_hash) VALUES (?,?,?)", (e, "Auditor", hash_pass(p)))
            conn.commit(); st.success("Registrado")
        except: st.error("Ya existe")
        conn.close()

if __name__ == "__main__":
    if 'user_id' not in st.session_state: vista_login()
    else: vista_principal()
