"""Prepara Ovum1_3.blend para simular los huevos con fisica (Rigid Body / Bullet).

- Huevos: cuerpos rigidos ACTIVOS (casco convexo, 60 g). Se quita su animacion por keyframes;
  las acciones originales se conservan con usuario falso (Huevo_XX_anim) por si se quieren volver a usar.
- Maquina: colisionadores PASIVOS (malla). Las piezas con movimiento (pasadores del escape, cuna
  basculante, canal giratorio) quedan como pasivos ANIMADOS, asi empujan y sueltan los huevos.
- Cepillos: sus cerdas no sirven como colision; se agregan cilindros invisibles que giran con ellos.
- Piso de colision en z=0. Mundo fisico con subpasos altos: los huevos son piezas pequenas (4 cm).

Uso: blender --background Ovum1_3.blend --python setup_fisica_ovum1_3.py -- [n_frames_prueba] [save]
"""
import bpy, bmesh, math, sys, json
from mathutils import Vector, Matrix, Euler

argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
TEST_FRAMES = int(argv[0]) if argv and argv[0].isdigit() else 0
SAVE = "save" in argv

sc = bpy.context.scene
vl = bpy.context.view_layer
FRAME_END = sc.frame_end

# ---------- parametros fisicos ----------
EGG_MASS = 0.060                 # kg
MARGIN = 0.0005                  # margen de colision (el valor por defecto, 4 cm, es enorme a esta escala)
MAT_PHYS = {                     # (friccion, rebote)
    "huevo": (0.6, 0.15),
    "acero": (0.35, 0.1),
    "caucho": (0.9, 0.05),
    "plastico": (0.5, 0.1),
    "cerdas": (0.9, 0.0),
}
ANIMADOS = {"Pasador_Delantero", "Pasador_Trasero", "Cuna_Basculante", "Canal_Giratorio"}
EXCLUIR = {"Cable_Alimentacion", "LED_Rojo", "LED_Verde", "Boton", "Leva_Escape", "Camara_Vision",
           "Cortinas_Caucho",   # son flexibles: como cuerpo rigido serian un muro
           "Cepillo_Cama_1", "Cepillo_Cama_2", "Cepillo_Superior"}
CAUCHO = {"Cuna_Basculante", "Cortinas_Caucho", "Patas_Niveladoras"}
ACERO = {"Rieles_Canaleta", "Guias_Canaleta", "Pasador_Delantero", "Pasador_Trasero", "Rampa_Rechazo",
         "Poste_Camara", "Poste_Camara.001", "Celda_Carga_Pesaje"}

def add_rb(o, kind):
    for ob in vl.objects: ob.select_set(False)
    o.select_set(True); vl.objects.active = o
    with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o], selected_editable_objects=[o]):
        bpy.ops.rigidbody.object_add(type=kind)
    return o.rigid_body

# ---------- mundo fisico ----------
if sc.rigidbody_world is None:
    bpy.ops.rigidbody.world_add()
rbw = sc.rigidbody_world
rbw.substeps_per_frame = 30
rbw.solver_iterations = 30
rbw.use_split_impulse = True
rbw.point_cache.frame_start = sc.frame_start
rbw.point_cache.frame_end = FRAME_END
sc.gravity = (0, 0, -9.81)

# ---------- piso ----------
if "Piso_Colision" not in bpy.data.objects:
    me = bpy.data.meshes.new("Piso_Colision")
    bm = bmesh.new(); g = bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.scale(bm, verts=g['verts'], vec=(3, 3, 0.1)); bmesh.ops.translate(bm, verts=g['verts'], vec=(0, 0, -0.05))
    bm.to_mesh(me); bm.free()
    piso = bpy.data.objects.new("Piso_Colision", me); sc.collection.objects.link(piso)
    piso.display_type = 'WIRE'; piso.hide_render = True
piso = bpy.data.objects["Piso_Colision"]

# ---------- huevos: posicion inicial (frame 1) y cuerpo activo ----------
eggs = sorted([o for o in bpy.data.objects if o.name.startswith("Huevo_") and o.type == 'MESH'], key=lambda o: o.name)
sc.frame_set(sc.frame_start)
start = {}
waiting = []
for o in eggs:
    if o.hide_render or o.hide_viewport: waiting.append(o)
    else: start[o.name] = o.matrix_world.copy()
# los huevos que aparecian despues esperan sobre la bandeja de carga (quietos, "animados") y se
# cargan a mano uno por ciclo de 2 s en la cola de la canaleta; desde ahi los mueve solo la gravedad
TANA = math.tan(math.radians(4))
def zrail(y): return 0.199 + (-0.075 - y)*TANA - 0.0245        # eje de los rieles de la canaleta
DROP = Vector((0.0, -0.545, zrail(-0.545) + 0.0245 + 0.012))
hold = [(x, y, layer) for layer in range(2) for y in (-0.555, -0.505, -0.455) for x in (-0.12, -0.07, 0.07, 0.12)]
def vtray_z(x, y): return zrail(y) + 0.004 + 0.002 + (abs(x)-0.03)*math.tan(math.radians(9))
RELEASE0, CYCLE = 40, 48
release = {}
for k, (o, (x, y, layer)) in enumerate(zip(waiting, hold)):
    p_hold = Vector((x, y, vtray_z(x, y) + 0.0225 + layer*0.045))
    start[o.name] = Matrix.Translation(p_hold) @ Euler((0, math.pi/2, 0), 'XYZ').to_matrix().to_4x4()
    release[o.name] = (RELEASE0 + k*CYCLE, p_hold)
for o in eggs:
    ad = o.animation_data
    if ad and ad.action:
        ad.action.use_fake_user = True
        ad.action.name = f"{o.name}_anim"
        o.animation_data_clear()
    o.hide_viewport = False; o.hide_render = False
    mw = start[o.name]
    o.parent = None
    o.rotation_mode = 'XYZ'
    o.matrix_world = mw
    rb = add_rb(o, 'ACTIVE')
    rb.collision_shape = 'CONVEX_HULL'
    rb.mass = EGG_MASS
    rb.friction, rb.restitution = MAT_PHYS["huevo"]
    rb.linear_damping = 0.05
    rb.angular_damping = 0.15            # resistencia a la rodadura
    rb.use_margin = True; rb.collision_margin = MARGIN
    rb.use_deactivation = False          # que no se "duerman" esperando en la fila
    if o.name in release:
        fr, p_hold = release[o.name]
        rb.kinematic = True;  rb.keyframe_insert("kinematic", frame=sc.frame_start)
        o.location = p_hold;  o.keyframe_insert("location", frame=fr-10)
        o.location = DROP + Vector((0, 0, 0.03)); o.keyframe_insert("location", frame=fr-3)
        o.location = DROP;    o.keyframe_insert("location", frame=fr)
        rb.keyframe_insert("kinematic", frame=fr)
        rb.kinematic = False; rb.keyframe_insert("kinematic", frame=fr+1)
        o.location = p_hold

# ---------- proxies de colision de los cepillos ----------
def brush_proxy(bname, r):
    b = bpy.data.objects.get(bname)
    if b is None: return None
    pname = f"{bname}_Colision"
    if pname in bpy.data.objects: return bpy.data.objects[pname]
    me = bpy.data.meshes.new(pname)
    bm = bmesh.new()
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=r, radius2=r, depth=0.09)
    bmesh.ops.rotate(bm, verts=g['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(90), 3, 'X'))   # eje Y local, como el cepillo
    bm.to_mesh(me); bm.free()
    p = bpy.data.objects.new(pname, me)
    for c in b.users_collection: c.objects.link(p)
    p.parent = b; p.matrix_parent_inverse = Matrix.Identity(4); p.location = (0, 0, 0)
    p.display_type = 'WIRE'; p.hide_render = True
    return p
proxies = [brush_proxy("Cepillo_Cama_1", 0.0245), brush_proxy("Cepillo_Cama_2", 0.0245), brush_proxy("Cepillo_Superior", 0.036)]
proxies = [p for p in proxies if p]

# ---------- guias inox en el modulo de limpieza (nueva pieza, detectada con la simulacion) ----------
if "Guias_Limpieza" not in bpy.data.objects:
    YB0, YB1 = -0.255, -0.125
    me = bpy.data.meshes.new("Guias_Limpieza"); bm = bmesh.new()
    for s_ in (-1, 1):
        vs = [bm.verts.new(v) for v in ((s_*0.034, YB0, zrail(YB0)+0.008), (s_*0.034, YB1, zrail(YB1)+0.008),
                                         (s_*0.034, YB1, zrail(YB1)+0.033), (s_*0.034, YB0, zrail(YB0)+0.033))]
        f = bm.faces.new(vs)
        ex = bmesh.ops.extrude_face_region(bm, geom=[f])
        bmesh.ops.translate(bm, verts=[v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)], vec=(s_*0.002, 0, 0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    if "Acero_Inox" in bpy.data.materials: me.materials.append(bpy.data.materials["Acero_Inox"])
    g_ = bpy.data.objects.new("Guias_Limpieza", me)
    (bpy.data.collections.get("Limpieza") or sc.collection).objects.link(g_)
    ACERO.add("Guias_Limpieza")
# rieles continuos a traves de la limpieza (cepillos de cama ranurados): sin ellos el huevo cae en el
# valle entre dos cepillos que giran en el mismo sentido y gira en su lugar sin avanzar
if "Rieles_Limpieza" not in bpy.data.objects:
    YB0, YB1 = -0.255, -0.125
    me = bpy.data.meshes.new("Rieles_Limpieza"); bm = bmesh.new()
    for s_ in (-1, 1):
        p0 = Vector((s_*0.015, YB0, zrail(YB0))); p1 = Vector((s_*0.015, YB1, zrail(YB1))); d = p1 - p0
        g = bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.004, radius2=0.004, depth=d.length)
        bmesh.ops.rotate(bm, verts=g['verts'], cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix())
        bmesh.ops.translate(bm, verts=g['verts'], vec=(p0+p1)/2)
    bm.to_mesh(me); bm.free()
    if "Acero_Inox" in bpy.data.materials: me.materials.append(bpy.data.materials["Acero_Inox"])
    r_ = bpy.data.objects.new("Rieles_Limpieza", me)
    (bpy.data.collections.get("Limpieza") or sc.collection).objects.link(r_)
    ACERO.add("Rieles_Limpieza")

# ---------- maquina: colisionadores pasivos ----------
machine = []
egg_names = {o.name for o in eggs}
for o in sc.objects:
    if o.type != 'MESH' or o.name in egg_names or o.name in EXCLUIR or o.rigid_body: continue
    if o.hide_render and o is not piso and o not in proxies: continue   # tapas ocultas: fuera de la simulacion
    machine.append(o)
for o in machine:
    rb = add_rb(o, 'PASSIVE')
    is_proxy = o in proxies
    rb.collision_shape = 'MESH'
    rb.mesh_source = 'FINAL'
    rb.kinematic = o.name in ANIMADOS or is_proxy
    if is_proxy: fr = MAT_PHYS["cerdas"]
    elif o.name in CAUCHO: fr = MAT_PHYS["caucho"]
    elif o.name in ACERO: fr = MAT_PHYS["acero"]
    else: fr = MAT_PHYS["plastico"]
    rb.friction, rb.restitution = fr
    rb.use_margin = True; rb.collision_margin = MARGIN

rbw.point_cache.frame_end = FRAME_END
sc.frame_set(sc.frame_start)

# ---------- prueba corta (no se guarda el cache) ----------
report = {"huevos": len(eggs), "pasivos": len(machine), "animados": sorted([o.name for o in machine if o.rigid_body.kinematic])}
if TEST_FRAMES:
    track = {}
    for f in range(sc.frame_start, sc.frame_start + TEST_FRAMES + 1):
        sc.frame_set(f)
        if f % 96 == 1 or f == sc.frame_start + TEST_FRAMES:
            track[f] = {o.name: [round(v, 3) for v in o.matrix_world.translation] for o in eggs[:8]}
    zs = {o.name: o.matrix_world.translation.z for o in eggs}
    report["prueba"] = {"frames": TEST_FRAMES, "debajo_del_piso": [n for n, z in zs.items() if z < -0.01],
                        "z_min": round(min(zs.values()), 3), "track": track}
    sc.frame_set(sc.frame_start)
    bpy.ops.ptcache.free_bake_all()
if SAVE:
    bpy.ops.wm.save_mainfile()
    report["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(report))
