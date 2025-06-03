from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Dict, Any, List
import io
import pandas as pd
import uuid
import traceback
from datetime import datetime

from config import supabase

# Función para convertir fechas de formato DD-MM-YYYY a YYYY-MM-DD
def convert_date_format(date_str):
    if not date_str or pd.isna(date_str):
        return None
    try:
        # Intentar varios formatos de fecha
        formats = ['%d-%m-%Y', '%d/%m/%Y', '%d-%b-%Y', '%d %b %Y']
        for fmt in formats:
            try:
                date_obj = datetime.strptime(str(date_str), fmt)
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                continue
        # Si ninguno funciona, devolver None
        print(f"No se pudo convertir la fecha: {date_str}")
        return None
    except Exception as e:
        print(f"Error al convertir fecha {date_str}: {str(e)}")
        return None

router = APIRouter()

@router.post("/upload-csv",
          summary="Cargar datos desde archivo CSV",
          description="Permite cargar datos masivamente desde un archivo CSV para diferentes entidades del sistema")
async def upload_csv(file: UploadFile = File(...), tipo: str = None):
    """Carga datos desde un archivo CSV."""
    try:
        print(f"Recibiendo archivo CSV: {file.filename}, tipo: {tipo}")
        
        # Leer el archivo CSV
        contents = await file.read()
        df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        
        print(f"Columnas en el CSV: {df.columns.tolist()}")
        print(f"Primeras 2 filas: {df.head(2).to_dict('records')}")
        
        # Inicializar contadores
        inserted = 0
        errors = []
        processed_data = []
        
        # Detectar el tipo de datos basado en las columnas presentes
        columnas = df.columns.tolist()
        
        # Verificar si es el formato completo que incluye todas las entidades
        if "estudiante_numero_documento" in columnas and "estudiante_programa_academico" in columnas:
            print("Procesando datos del formato completo...")
            
            # Primero verificar la estructura de la tabla estudiantes
            try:
                # Verificar si la tabla estudiantes existe y tiene las columnas necesarias
                table_info = supabase.table("estudiantes").select("*").limit(1).execute()
                
                # Si llegamos aquí, la tabla existe, pero necesitamos verificar sus columnas
                # Esto lo haremos indirectamente intentando obtener la estructura
                print("Tabla estudiantes encontrada, verificando estructura...")
                
                # Obtener un registro para ver la estructura
                if table_info.data and len(table_info.data) > 0:
                    print(f"Estructura de la tabla estudiantes: {list(table_info.data[0].keys())}")
                    
                    # Guardar las columnas disponibles para usarlas después
                    columnas_disponibles = list(table_info.data[0].keys())
                else:
                    print("No se encontraron registros en la tabla estudiantes")
                    columnas_disponibles = ["id", "documento", "tipo_documento", "nombres", "apellidos", "correo", "programa_academico", "semestre"]
            except Exception as e:
                print(f"Error al verificar la tabla estudiantes: {str(e)}")
                # Podría ser que la tabla no existe o hay otro problema
                columnas_disponibles = ["id", "documento", "tipo_documento", "nombres", "apellidos", "correo", "programa_academico", "semestre"]
            
            # Procesar cada fila del CSV
            for index, row in df.iterrows():
                try:
                    # 1. Primero, buscar o crear el estudiante
                    documento = str(row["estudiante_numero_documento"]) if pd.notna(row["estudiante_numero_documento"]) else None
                    programa_academico = str(row["estudiante_programa_academico"]) if pd.notna(row["estudiante_programa_academico"]) else None
                    
                    if not documento:
                        raise ValueError("El número de documento del estudiante es obligatorio")
                    
                    # Buscar si el estudiante ya existe
                    estudiante_existente = supabase.table("estudiantes").select("*").eq("documento", documento).execute()
                    
                    estudiante_id = None
                    
                    if estudiante_existente.data and len(estudiante_existente.data) > 0:
                        # El estudiante ya existe, usar su ID
                        estudiante_id = estudiante_existente.data[0]["id"]
                        print(f"Estudiante encontrado con ID: {estudiante_id}")
                    else:
                        # Crear un nuevo estudiante
                        # Primero, buscar o crear el programa
                        programa_id = None
                        if programa_academico:
                            programa = supabase.table("programas").select("id").eq("nombre", programa_academico).execute()
                            if programa.data and len(programa.data) > 0:
                                programa_id = programa.data[0]["id"]
                            else:
                                # Crear un nuevo programa
                                nuevo_programa = {
                                    "nombre": programa_academico,
                                    "facultad": "Sin asignar",
                                    "codigo": f"PROG-{len(programa_academico)}-{str(uuid.uuid4())[:8]}",
                                    "nivel": "Pregrado"  # Valor por defecto para el campo obligatorio
                                }
                                programa_response = supabase.table("programas").insert(nuevo_programa).execute()
                                programa_id = programa_response.data[0]["id"]
                        
                        # Crear el estudiante - Usar solo campos que sabemos que existen
                        # Extraer el semestre si está disponible en el CSV
                        semestre = None
                        if "estudiante_semestre" in row and pd.notna(row["estudiante_semestre"]):
                            try:
                                semestre = int(row["estudiante_semestre"])
                            except:
                                semestre = 1
                        else:
                            semestre = 1  # Valor por defecto
                            
                        estudiante_data = {
                            "documento": documento,
                            "tipo_documento": "CC",  # Valor por defecto
                            "nombres": f"Estudiante {documento}",  # Siempre proporcionar un valor para nombres
                            "apellidos": f"Apellido {documento}",   # Siempre proporcionar un valor para apellidos
                            "correo": f"{documento}@ejemplo.com",   # Siempre proporcionar un valor para correo
                            "programa_academico": programa_academico or "Programa no especificado",  # Siempre proporcionar un valor para programa_academico
                            "semestre": semestre  # Siempre proporcionar un valor para semestre
                        }
                        
                        # Agregar programa_id si existe la columna
                        if "programa_id" in columnas_disponibles and programa_id:
                            estudiante_data["programa_id"] = programa_id
                        
                        # Agregar campos adicionales si están disponibles en la tabla
                        if "semestre" in columnas_disponibles and "estudiante_semestre" in row and pd.notna(row["estudiante_semestre"]):
                            try:
                                estudiante_data["semestre"] = int(row["estudiante_semestre"])
                            except:
                                estudiante_data["semestre"] = 1
                        
                        if "estrato" in columnas_disponibles and "estudiante_estrato" in row and pd.notna(row["estudiante_estrato"]):
                            try:
                                estudiante_data["estrato"] = int(row["estudiante_estrato"])
                            except:
                                estudiante_data["estrato"] = 1
                        
                        if "riesgo_desercion" in columnas_disponibles and "estudiante_riesgo_desercion" in row and pd.notna(row["estudiante_riesgo_desercion"]):
                            estudiante_data["riesgo_desercion"] = str(row["estudiante_riesgo_desercion"]).lower()
                        
                        # Crear el estudiante
                        print(f"Creando nuevo estudiante: {estudiante_data}")
                        try:
                            estudiante_response = supabase.table("estudiantes").insert(estudiante_data).execute()
                            if estudiante_response.data and len(estudiante_response.data) > 0:
                                estudiante_id = estudiante_response.data[0]["id"]
                                print(f"Estudiante creado con ID: {estudiante_id}")
                            else:
                                print(f"Error al crear estudiante, respuesta vacía")
                                raise Exception("No se pudo crear el estudiante, respuesta vacía")
                        except Exception as e:
                            print(f"Error en fila {index+1}: {e}")
                            if hasattr(e, 'json'):
                                error_json = e.json()
                                print(f"Error en fila {index+1}: {error_json}")
                            raise e
                    
                    # 2. Procesar datos de POVAU si corresponde
                    if "POVAU_tipo_participante" in row and pd.notna(row["POVAU_tipo_participante"]) and estudiante_id:
                        try:
                            povau_data = {
                                "estudiante_id": estudiante_id,
                                "tipo_participante": str(row["POVAU_tipo_participante"]),
                                "fecha_ingreso": convert_date_format(row["POVAU_fecha_ingreso_programa"]) if pd.notna(row["POVAU_fecha_ingreso_programa"]) else None
                            }
                            
                            # Insertar en POVAU
                            print(f"Creando registro POVAU: {povau_data}")
                            supabase.table("povau").insert(povau_data).execute()
                            print("Registro POVAU creado correctamente")
                        except Exception as e:
                            print(f"Error al crear registro POVAU: {str(e)}")
                            # No interrumpir el proceso si falla la creación del registro
                    
                    # 3. Procesar datos de POA si corresponde
                    if "POA_ciclo_formacion" in row and pd.notna(row["POA_ciclo_formacion"]) and estudiante_id:
                        try:
                            poa_data = {
                                "estudiante_id": estudiante_id,
                                "ciclo_formacion": str(row["POA_ciclo_formacion"]),
                                "nombre_asignatura": str(row["POA_nombre_asignatura"]) if pd.notna(row["POA_nombre_asignatura"]) else None,
                                "fecha": convert_date_format(row["POA_fecha"]) if pd.notna(row["POA_fecha"]) else None
                            }
                            
                            # Insertar en POA
                            print(f"Creando registro POA: {poa_data}")
                            supabase.table("poa").insert(poa_data).execute()
                            print("Registro POA creado correctamente")
                        except Exception as e:
                            print(f"Error al crear registro POA: {str(e)}")
                            # No interrumpir el proceso si falla la creación del registro
                    
                    # 4. Procesar datos de Comedor Universitario si corresponde
                    if "ComedorUniversitario_condicion_socioeconomica" in row and pd.notna(row["ComedorUniversitario_condicion_socioeconomica"]) and estudiante_id:
                        try:
                            # Obtener datos del estudiante para completar campos obligatorios
                            estudiante_info = supabase.table("estudiantes").select("*").eq("id", estudiante_id).execute()
                            nombre_estudiante = ""
                            if estudiante_info.data and len(estudiante_info.data) > 0:
                                nombre_estudiante = f"{estudiante_info.data[0].get('nombres', '')} {estudiante_info.data[0].get('apellidos', '')}"
                            
                            comedor_data = {
                                "estudiante_id": estudiante_id,
                                "condicion_socioeconomica": str(row["ComedorUniversitario_condicion_socioeconomica"]),
                                "fecha_solicitud": convert_date_format(row["ComedorUniversitario_fecha_solicitud"]) if pd.notna(row["ComedorUniversitario_fecha_solicitud"]) else datetime.now().strftime('%Y-%m-%d'),
                                "aprobado": bool(row["ComedorUniversitario_aprobado"]) if pd.notna(row["ComedorUniversitario_aprobado"]) else False,
                                "tipo_comida": "Almuerzo",  # Campo obligatorio
                                "raciones_asignadas": 1,  # Campo obligatorio
                                "observaciones": "Importado desde CSV"
                            }
                            
                            # Insertar en Comedor
                            print(f"Creando registro Comedor con tipo_comida: {comedor_data}")
                            supabase.table("comedor_universitario").insert(comedor_data).execute()
                            print("Registro Comedor creado correctamente")
                        except Exception as e:
                            print(f"Error al crear registro Comedor: {str(e)}")
                            # No interrumpir el proceso si falla la creación del registro
                    
                    # 5. Procesar datos de Registro de Beneficio si corresponde
                    if "RegistroBeneficio_fecha_inscripcion" in row and pd.notna(row["RegistroBeneficio_fecha_inscripcion"]) and estudiante_id:
                        try:
                            beneficio_data = {
                                "estudiante_id": estudiante_id,
                                "fecha_inscripcion": convert_date_format(row["RegistroBeneficio_fecha_inscripcion"]),
                                "estado_solicitud": bool(row["RegistroBeneficio_estado_solicitud"]) if pd.notna(row["RegistroBeneficio_estado_solicitud"]) else False,
                                "periodo_academico": str(row["RegistroBeneficio_periodo_academico_beneficiado"]) if pd.notna(row["RegistroBeneficio_periodo_academico_beneficiado"]) else None,
                                "fecha_inicio": convert_date_format(row["RegistroBeneficio_fecha_inicio_servicio"]) if pd.notna(row["RegistroBeneficio_fecha_inicio_servicio"]) else None,
                                "fecha_finalizacion": convert_date_format(row["RegistroBeneficio_fecha_finalizacion_servicio"]) if pd.notna(row["RegistroBeneficio_fecha_finalizacion_servicio"]) else None
                            }
                            
                            # Insertar el registro de beneficio
                            print(f"Creando registro de beneficio: {beneficio_data}")
                            supabase.table("registro_beneficios").insert(beneficio_data).execute()
                            print("Registro de beneficio creado correctamente")
                        except Exception as e:
                            print(f"Error al crear registro de beneficio: {str(e)}")
                            # No interrumpir el proceso si falla la creación del registro
                    
                    # 6. Procesar datos de Solicitud de Atención Individual si corresponde
                    if "SolicitudAtencionIndividual_fecha_atencion" in row and pd.notna(row["SolicitudAtencionIndividual_fecha_atencion"]) and estudiante_id:
                        try:
                            atencion_data = {
                                "estudiante_id": estudiante_id,
                                "fecha_atencion": convert_date_format(row["SolicitudAtencionIndividual_fecha_atencion"]),
                                "motivo_atencion": str(row["SolicitudAtencionIndividual_motivo_atencion"]) if pd.notna(row["SolicitudAtencionIndividual_motivo_atencion"]) else "general"
                            }
                            
                            # Insertar la solicitud de atención
                            print(f"Creando solicitud de atención: {atencion_data}")
                            supabase.table("solicitudes_atencion").insert(atencion_data).execute()
                            print("Solicitud de atención creada correctamente")
                        except Exception as e:
                            print(f"Error al crear solicitud de atención: {str(e)}")
                            # No interrumpir el proceso si falla la creación del registro
                    
                    # 7. Procesar datos de Intervención Grupal si corresponde
                    if "IntervencionGrupal_fecha_solicitud" in row and pd.notna(row["IntervencionGrupal_fecha_solicitud"]) and estudiante_id:
                        try:
                            # Crear un diccionario con todos los campos posibles de intervenciones grupales
                            intervencion_data = {
                                "estudiante_id": estudiante_id,
                                "fecha_solicitud": convert_date_format(row["IntervencionGrupal_fecha_solicitud"]) or datetime.now().strftime('%Y-%m-%d'),
                                "fecha_recepcion": convert_date_format(row["IntervencionGrupal_fecha_recepcion"]) if pd.notna(row.get("IntervencionGrupal_fecha_recepcion")) else None,
                                "nombre_docente_permanencia": str(row["IntervencionGrupal_nombre_docente_permanencia"]) if pd.notna(row.get("IntervencionGrupal_nombre_docente_permanencia")) else "Docente por defecto",
                                "celular_permanencia": str(row["IntervencionGrupal_celular_permanencia"]) if pd.notna(row.get("IntervencionGrupal_celular_permanencia")) else "0000000000",
                                "correo_permanencia": str(row["IntervencionGrupal_correo_permanencia"]) if pd.notna(row.get("IntervencionGrupal_correo_permanencia")) else f"permanencia_{estudiante_id}@ejemplo.com",
                                "estudiante_programa_academico_permanencia": str(row["IntervencionGrupal_programa_permanencia"]) if pd.notna(row.get("IntervencionGrupal_programa_permanencia")) else programa_academico or "Programa no especificado",
                                "tipo_poblacion": str(row["IntervencionGrupal_tipo_poblacion"]) if pd.notna(row.get("IntervencionGrupal_tipo_poblacion")) else "General",
                                "nombre_docente_asignatura": str(row["IntervencionGrupal_nombre_docente_asignatura"]) if pd.notna(row.get("IntervencionGrupal_nombre_docente_asignatura")) else "Docente asignatura",
                                "celular_docente_asignatura": str(row["IntervencionGrupal_celular_docente_asignatura"]) if pd.notna(row.get("IntervencionGrupal_celular_docente_asignatura")) else "0000000000",
                                "correo_docente_asignatura": str(row["IntervencionGrupal_correo_docente_asignatura"]) if pd.notna(row.get("IntervencionGrupal_correo_docente_asignatura")) else f"docente_{estudiante_id}@ejemplo.com",
                                "estudiante_programa_academico_docente_asignatura": str(row["IntervencionGrupal_programa_docente_asignatura"]) if pd.notna(row.get("IntervencionGrupal_programa_docente_asignatura")) else programa_academico or "Programa no especificado",
                                "asignatura_intervenir": str(row["IntervencionGrupal_asignatura_intervenir"]) if pd.notna(row.get("IntervencionGrupal_asignatura_intervenir")) else "Asignatura general",
                                "grupo": str(row["IntervencionGrupal_grupo"]) if pd.notna(row.get("IntervencionGrupal_grupo")) else "1",
                                "semestre": str(row["IntervencionGrupal_semestre"]) if pd.notna(row.get("IntervencionGrupal_semestre")) else str(row.get("estudiante_semestre", "1")) if pd.notna(row.get("estudiante_semestre")) else "1",
                                "numero_estudiantes": str(row["IntervencionGrupal_numero_estudiantes"]) if pd.notna(row.get("IntervencionGrupal_numero_estudiantes")) else "1",
                                "tematica_sugerida": str(row["IntervencionGrupal_tematica_sugerida"]) if pd.notna(row.get("IntervencionGrupal_tematica_sugerida")) else None,
                                "fecha_estudiante_programa_academicoda": convert_date_format(row["IntervencionGrupal_fecha_programada"]) if pd.notna(row.get("IntervencionGrupal_fecha_programada")) else datetime.now().strftime('%Y-%m-%d'),
                                "hora": str(row["IntervencionGrupal_hora"]) if pd.notna(row.get("IntervencionGrupal_hora")) else "08:00",
                                "aula": str(row["IntervencionGrupal_aula"]) if pd.notna(row.get("IntervencionGrupal_aula")) else "Aula por asignar",
                                "bloque": str(row["IntervencionGrupal_bloque"]) if pd.notna(row.get("IntervencionGrupal_bloque")) else "Bloque por asignar",
                                "sede": str(row["IntervencionGrupal_sede"]) if pd.notna(row.get("IntervencionGrupal_sede")) else "Sede principal",
                                "estado": str(row["IntervencionGrupal_estado"]) if pd.notna(row.get("IntervencionGrupal_estado")) else "espera",
                                "motivo": str(row["IntervencionGrupal_motivo"]) if pd.notna(row.get("IntervencionGrupal_motivo")) else None,
                                "efectividad": str(row["IntervencionGrupal_efectividad"]) if pd.notna(row.get("IntervencionGrupal_efectividad")) else "Pendiente evaluación"
                            }
                            
                            # Si el estado no es "se hizo" y no hay motivo, establecer un motivo por defecto
                            if intervencion_data.get("estado") != "se hizo" and not intervencion_data.get("motivo"):
                                intervencion_data["motivo"] = "Importado desde CSV"
                            
                            # Insertar la intervención grupal
                            print(f"Creando intervención grupal: {intervencion_data}")
                            supabase.table("intervenciones_grupales").insert(intervencion_data).execute()
                            print("Intervención grupal creada correctamente")
                        except Exception as e:
                            print(f"Error al crear intervención grupal: {str(e)}")
                            # No interrumpir el proceso si falla la creación del registro
                    
                    # 8. Procesar remisiones psicológicas si corresponde
                    if "RemisionPsicologica_fecha_remision" in row and pd.notna(row["RemisionPsicologica_fecha_remision"]) and estudiante_id:
                        try:
                            # Obtener datos del estudiante para completar campos obligatorios
                            estudiante_info = supabase.table("estudiantes").select("*").eq("id", estudiante_id).execute()
                            nombre_estudiante = ""
                            numero_documento = ""
                            programa_academico = ""
                            semestre = "1"
                            
                            if estudiante_info.data and len(estudiante_info.data) > 0:
                                nombre_estudiante = f"{estudiante_info.data[0].get('nombres', '')} {estudiante_info.data[0].get('apellidos', '')}"
                                numero_documento = estudiante_info.data[0].get('documento', '')
                                programa_academico = estudiante_info.data[0].get('programa_academico', '')
                                semestre = str(estudiante_info.data[0].get('semestre', '1'))
                            else:
                                # Si no se encuentra el estudiante, usar datos del CSV
                                nombre_estudiante = f"Estudiante {row['estudiante_numero_documento']}" if pd.notna(row.get('estudiante_numero_documento')) else "Estudiante sin nombre"
                                numero_documento = str(row['estudiante_numero_documento']) if pd.notna(row.get('estudiante_numero_documento')) else "0000000000"
                                programa_academico = str(row['estudiante_programa_academico']) if pd.notna(row.get('estudiante_programa_academico')) else "No especificado"
                                semestre = str(row['estudiante_semestre']) if pd.notna(row.get('estudiante_semestre')) else "1"
                            
                            remision_psico_data = {
                                "estudiante_id": estudiante_id,
                                "nombre_estudiante": nombre_estudiante,
                                "numero_documento": numero_documento,
                                "programa_academico": programa_academico,
                                "semestre": semestre,
                                "motivo_remision": "Importado desde CSV",  # Campo obligatorio
                                "docente_remite": "Docente CSV",  # Campo obligatorio
                                "correo_docente": "docente_csv@ejemplo.com",  # Campo obligatorio
                                "telefono_docente": "0000000000",  # Campo obligatorio
                                "fecha": convert_date_format(row["RemisionPsicologica_fecha_remision"]) or datetime.now().strftime('%Y-%m-%d'),  # Campo obligatorio
                                "hora": "12:00",  # Campo obligatorio
                                "tipo_remision": str(row["RemisionPsicologica_tipo_remision"]) if pd.notna(row["RemisionPsicologica_tipo_remision"]) else "individual",  # Campo obligatorio
                                "fecha_remision": convert_date_format(row["RemisionPsicologica_fecha_remision"]) or datetime.now().strftime('%Y-%m-%d'),
                                "observaciones": "Importado automáticamente desde CSV"
                            }
                            
                            # Insertar la remisión psicológica
                            print(f"Creando remisión psicológica con todos los campos obligatorios: {remision_psico_data}")
                            supabase.table("remisiones_psicologicas").insert(remision_psico_data).execute()
                            print("Remisión psicológica creada correctamente")
                        except Exception as e:
                            print(f"Error al crear remisión psicológica: {str(e)}")
                            # No interrumpir el proceso si falla la creación del registro
                    
                    # 9. Procesar formato de asistencia si corresponde
                    if "FormatoAsistencia_numero_asistencia" in row and pd.notna(row["FormatoAsistencia_numero_asistencia"]) and estudiante_id:
                        try:
                            asistencia_data = {
                                "estudiante_id": estudiante_id,
                                "numero_asistencia": int(row["FormatoAsistencia_numero_asistencia"]) if pd.notna(row["FormatoAsistencia_numero_asistencia"]) else 1,
                                "fecha": convert_date_format(row["FormatoAsistencia_fecha"]) if pd.notna(row["FormatoAsistencia_fecha"]) else None
                            }
                            
                            # Insertar el formato de asistencia
                            print(f"Creando formato de asistencia: {asistencia_data}")
                            supabase.table("formatos_asistencia").insert(asistencia_data).execute()
                            print("Formato de asistencia creado correctamente")
                        except Exception as e:
                            print(f"Error al crear formato de asistencia: {str(e)}")
                            # No interrumpir el proceso si falla la creación del registro
                    
                    # 10. Procesar datos de permanencia
                    # Crear un registro en la tabla permanencia para estadísticas
                    try:
                        permanencia_data = {
                            "servicio": "POA" if pd.notna(row.get("POA_ciclo_formacion")) else 
                                      "POVAU" if pd.notna(row.get("POVAU_tipo_participante")) else
                                      "Comedor" if pd.notna(row.get("ComedorUniversitario_condicion_socioeconomica")) else
                                      "POPS" if pd.notna(row.get("RemisionPsicologica_fecha_remision")) else
                                      "Intervención Grupal" if pd.notna(row.get("IntervencionGrupal_fecha_solicitud")) else
                                      "Atención Individual" if pd.notna(row.get("SolicitudAtencionIndividual_fecha_atencion")) else
                                      "Otro",
                            "estrato": int(row["estudiante_estrato"]) if pd.notna(row.get("estudiante_estrato")) else 1,
                            "inscritos": 1,  # Cada registro representa un estudiante inscrito
                            "estudiante_programa_academico": programa_academico,
                            "riesgo_desercion": str(row["estudiante_riesgo_desercion"]).lower() if pd.notna(row.get("estudiante_riesgo_desercion")) else "bajo",
                            "tipo_vulnerabilidad": "Académica",  # Valor por defecto
                            "periodo": str(row["RegistroBeneficio_periodo_academico_beneficiado"]) if pd.notna(row.get("RegistroBeneficio_periodo_academico_beneficiado")) else "2023-1",
                            "semestre": int(row["estudiante_semestre"]) if pd.notna(row.get("estudiante_semestre")) else 1,
                            "matriculados": 1,  # Por defecto, asumimos que están matriculados
                            "desertores": 0,  # Por defecto, no son desertores
                            "graduados": 0,  # Por defecto, no son graduados
                            "requiere_tutoria": "Sí" if str(row.get("estudiante_riesgo_desercion", "")).lower() in ["alto", "muy alto"] else "No"
                        }
                        
                        # Insertar en la tabla permanencia
                        print(f"Creando registro de permanencia: {permanencia_data}")
                        supabase.table("permanencia").insert(permanencia_data).execute()
                    except Exception as e:
                        print(f"Error al crear registro de permanencia: {str(e)}")
                        # No interrumpir el proceso si falla la creación del registro de permanencia
                    
                    # Añadir a los datos procesados
                    processed_data.append({
                        "documento": documento,
                        "programa": programa_academico,
                        "estudiante_id": estudiante_id,
                        "procesado": True
                    })
                    
                    inserted += 1
                    
                except Exception as e:
                    error_msg = f"Error en fila {index+1}: {str(e)}"
                    print(error_msg)
                    print(f"Traceback: {traceback.format_exc()}")
                    errors.append(error_msg)
                    
                    # Añadir a los datos procesados con error
                    processed_data.append({
                        "documento": str(row["estudiante_numero_documento"]) if pd.notna(row["estudiante_numero_documento"]) else "N/A",
                        "programa": str(row["estudiante_programa_academico"]) if pd.notna(row["estudiante_programa_academico"]) else "N/A",
                        "error": str(e),
                        "procesado": False
                    })
        else:
            # Formato no reconocido
            return {
                "success": False,
                "data": [],
                "inserted": 0,
                "error": "Formato de CSV no reconocido. Debe contener al menos las columnas: estudiante_numero_documento, estudiante_programa_academico"
            }
        
        # Retornar respuesta en el formato que espera el frontend
        return {
            "success": True,
            "data": processed_data,  # Enviar los datos procesados
            "inserted": inserted,
            "errors": errors,
            "message": f"Se procesaron {inserted} registros correctamente."
        }
            
    except Exception as e:
        error_msg = f"Error al procesar el archivo CSV: {str(e)}"
        print(error_msg)
        print(f"Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "data": [],
            "inserted": 0,
            "errors": [error_msg],
            "message": "Ocurrió un error al procesar el archivo CSV. Por favor, verifica el formato e intenta nuevamente."
        }
