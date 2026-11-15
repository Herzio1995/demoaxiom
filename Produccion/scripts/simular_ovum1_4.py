"""Simulacion de Ovum1_4 con el mecanismo nuevo del usuario (solo objetos visibles = disenados).

Mecanismo:
  rieles -> plato de pesaje concavo (PesadorBase.001, fijo sobre la barra Cube.002) donde el huevo se
  detiene solo -> gancho en C (Cylinder) que gira sobre el eje X de su varilla y saca el huevo del plato ->
  redireccionador (RedireccionadorBase.001) que gira sobre el eje vertical del plato y orienta su salida
  hacia una de las 4 bandejas.

Modos:
  -- explorar   : prueba giros del gancho y angulos del redireccionador (no guarda)
  -- prueba     : configura todo y simula la escena completa (no guarda)
  -- save       : configura todo y guarda el archivo
"""
import bpy, bmesh, sys, json, math, random
from mathutils import Vector, Matrix, Euler

argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
sc = bpy.context.scene
vl = bpy.context.view_layer
rbw = sc.rigidbody_world
MARGIN = 0.0005

def add_rb(o, kind):
    if o.rigid_body: return o.rigid_body
    for ob in vl.objects: ob.select_set(False)
    o.select_set(True); vl.objects.active = o
    with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o], selected_editable_objects=[o]):
        bpy.ops.rigidbody.object_add(type=kind)
    return o.rigid_body
def remove_rb(o):
    if not o.rigid_body: return
    for ob in vl.objects: ob.select_set(False)
    o.select_set(True); vl.objects.active = o
    with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o], selected_editable_objects=[o]):
        bpy.ops.rigidbody.object_remove()
def curves(o):
    ad = o.animation_data
    if not ad or not ad.action: return []
    try: return [fc for ly in ad.action.layers for st in ly.strips for fc in st.channelbag(ad.action_slot).fcurves]
    except AttributeError: return list(ad.action.fcurves)
def key_rot(o, idx, f, val, interp='BEZIER'):
    o.rotation_euler[idx] = val; o.keyframe_insert("rotation_euler", index=idx, frame=f)
    for fc in curves(o):
        if fc.data_path == "rotation_euler" and fc.array_index == idx:
            for kp in fc.keyframe_points:
                if int(round(kp.co.x)) == f: kp.interpolation = interp
def reset_cache():
    rbw.point_cache.frame_start = rbw.point_cache.frame_start   # marca el cache como desactualizado
    sc.frame_set(sc.frame_start)

# ---------- 1. solo lo disenado: los objetos ocultos salen de la simulacion ----------
removed = []
for o in list(sc.objects):
    if o.rigid_body and (o.hide_get() or o.hide_viewport) and not o.name.endswith("_Colision"):
        remove_rb(o); removed.append(o.name)

# ---------- 2. piezas nuevas con colision ----------
plato = bpy.data.objects["PesadorBase.001"]
barra = bpy.data.objects["Cube.002"]
gancho = bpy.data.objects["Cylinder"]
redir = bpy.data.objects["RedireccionadorBase.001"]
for o, fr, kin in ((plato, 0.9, False), (barra, 0.5, False), (gancho, 0.6, True), (redir, 0.35, True)):
    rb = add_rb(o, 'PASSIVE')
    rb.collision_shape = 'MESH'; rb.mesh_source = 'FINAL'
    rb.friction, rb.restitution = fr, 0.05
    rb.use_margin = True; rb.collision_margin = MARGIN
    rb.kinematic = kin
PLATO_C = Vector((0.0, -0.0615, 0.0))          # centro del plato (eje del redireccionador)
PIV = gancho.matrix_world.translation.copy()   # eje del gancho (paralelo a X)

eggs = sorted([o for o in bpy.data.objects if o.name.startswith("Huevo_")], key=lambda o: o.name)
for o in eggs:
    if o.rigid_body: o.rigid_body.collision_shape = 'CAPSULE'

def tray_under(p, depth=0.4):
    dg = bpy.context.evaluated_depsgraph_get(); origin = p.copy()
    for _ in range(8):
        ok, loc, nrm, idx, ob, m = sc.ray_cast(dg, origin, Vector((0, 0, -1)), distance=depth)
        if not ok: return None
        if ob.name.startswith("Huevo_") or not ob.rigid_body: origin = loc + Vector((0, 0, -0.0005)); continue
        return ob.name

# ======================================================================================
if "explorar" in argv:
    out = {"sin_fisica_ocultos": removed}
    # (a) salida del redireccionador: a que bandeja apunta segun su giro
    phi0 = redir.rotation_euler.z
    ws = [v.co for v in redir.data.vertices]
    # la salida es el punto mas lejano del eje en planta (coordenadas locales)
    far = max(ws, key=lambda v: v.xy.length)
    out["salida_local_deg"] = round(math.degrees(math.atan2(far.y, far.x)), 1)
    mapping = {}
    for deg in range(-120, 121, 10):
        redir.rotation_euler.z = math.radians(deg); vl.update()
        tip = redir.matrix_world @ (far * 1.0)
        mapping[deg] = tray_under(tip + Vector((0, 0, 0.01)) + (tip - redir.matrix_world.translation).normalized()*0.015)
    out["redir_giro_vs_bandeja"] = mapping
    redir.rotation_euler.z = phi0
    # (b) giro del gancho: un huevo en el plato, el resto fuera de la simulacion
    test = eggs[0]
    for o in eggs[1:]:
        if o.name in rbw.collection.objects: rbw.collection.objects.unlink(o)
    test.animation_data_clear(); test.rigid_body.kinematic = False
    test.rotation_mode = 'XYZ'
    def run(theta_rest, delta, redir_deg=None):
        gancho.animation_data_clear()
        key_rot(gancho, 0, 1, math.radians(theta_rest)); key_rot(gancho, 0, 25, math.radians(theta_rest))
        key_rot(gancho, 0, 37, math.radians(theta_rest + delta)); key_rot(gancho, 0, 60, math.radians(theta_rest + delta))
        if redir_deg is not None: redir.rotation_euler.z = math.radians(redir_deg)
        test.matrix_world = Matrix.Translation((0.0, -0.0615, 0.20)) @ Euler((0, math.pi/2, 0)).to_matrix().to_4x4()
        reset_cache()
        traj = {}
        for f in range(1, 101):
            sc.frame_set(f)
            if f in (24, 36, 44, 60, 100): traj[f] = [round(v, 3) for v in test.matrix_world.translation]
        return traj, tray_under(test.matrix_world.translation)
    res = {}
    for theta_rest in (146,):
        for delta in (60, 90, 120, 150, 180, -60, -90, -120):
            traj, t = run(theta_rest, delta)
            res[f"{theta_rest}{delta:+d}"] = {"traj": traj, "termina_en": t}
    out["gancho"] = res
    # repetibilidad del reinicio de cache
    traj, t = run(146, 120); out["repeticion_146+120"] = {"traj": traj, "termina_en": t}
    print("RESULT " + json.dumps(out))
    raise SystemExit

if "explorar2" in argv:
    out = {}
    # centro real del plato: centroide del borde superior
    ws = [plato.matrix_world @ v.co for v in plato.data.vertices]
    ztop = max(w.z for w in ws)
    rim = [w for w in ws if w.z > ztop - 0.0003]
    cx = sum(w.x for w in rim)/len(rim); cy = sum(w.y for w in rim)/len(rim)
    rmax = max(math.hypot(w.x-cx, w.y-cy) for w in rim)
    low = min(ws, key=lambda w: w.z if math.hypot(w.x-cx, w.y-cy) < 0.03 else 9)
    out["plato_centro"] = [round(cx, 4), round(cy, 4)]; out["plato_radio"] = round(rmax, 4); out["pivote"] = [round(v, 4) for v in PIV]
    test = eggs[0]
    for o in eggs[1:]:
        if o.name in rbw.collection.objects: rbw.collection.objects.unlink(o)
    test.animation_data_clear(); test.rigid_body.kinematic = False; test.rotation_mode = 'XYZ'
    TANA = math.tan(math.radians(4))
    def ez(y): return 0.199 + (-0.075 - y)*TANA
    def run(theta_rest, delta, f_push=40, dur=12):
        gancho.animation_data_clear()
        key_rot(gancho, 0, 1, math.radians(theta_rest)); key_rot(gancho, 0, f_push, math.radians(theta_rest))
        key_rot(gancho, 0, f_push+dur, math.radians(theta_rest + delta)); key_rot(gancho, 0, f_push+dur+30, math.radians(theta_rest + delta))
        redir.rotation_euler.z = 0.0          # salida hacia Bandeja 2.001
        test.matrix_world = Matrix.Translation((0.0, -0.16, ez(-0.16))) @ Euler((0, math.pi/2, 0)).to_matrix().to_4x4()
        reset_cache()
        traj = {}
        for f in range(1, f_push+dur+60):
            sc.frame_set(f)
            if f in (20, f_push-1, f_push+dur//2, f_push+dur, f_push+dur+10, f_push+dur+58): traj[f] = [round(v, 3) for v in test.matrix_world.translation]
        return traj, tray_under(test.matrix_world.translation + Vector((0, 0, -0.022)))
    res = {}
    for theta_rest in (131, 120, 145):
        for delta in (100, 130, 160, 190):
            traj, t = run(theta_rest, delta)
            res[f"{theta_rest}{delta:+d}"] = {"traj": traj, "termina_en": t}
    out["gancho"] = res
    print("RESULT " + json.dumps(out))
    raise SystemExit

# ======================================================================================
# CONFIGURACION FINAL
# ======================================================================================
TC = 72                                   # 3 s por huevo = 1200 huevos/h (ciclo probado; ver notas para acortarlo)
P0 = 40                                   # primer ciclo (el primer huevo ya esta en el plato)
THETA_REST = 145.0                        # gancho en reposo: abertura hacia los rieles, arco por delante y encima del huevo
OPEN = 125.0                              # el gancho gira +125: abre el frente y empuja suave por detras
TILT = -38.0                              # el plato bascula 38 grados sobre su borde delantero (con 30 el borde concavo a veces lo retenia)
# ciclo (relativo a F(c)):  gancho abre 0-10, el plato bascula 8-16 y vuelve 30-38, el gancho cierra 40-52,
#                           el pasador baja 55-81 y deja entrar al siguiente huevo; el redireccionador gira 0-8
#                           (justo antes de que el plato bascule: el huevo anterior ya salio hace mas de 30 frames)
def gancho_keys(f0, _a0=None):
    for f_, a_ in ((0, 0), (10, OPEN), (40, OPEN), (52, 0)):
        key_rot(gancho, 0, f0+f_, math.radians(THETA_REST + a_), 'BEZIER')
CYCLE_GANCHO = 52
PLATO_PIVOT = Vector((0.0, -0.054 + 0.046, 0.177))   # borde delantero del plato (eje X)
def plato_basculante():
    """el plato pasa a girar sobre su borde delantero: se mueve el origen al eje sin mover la geometria"""
    if plato.get("basculante"): return
    mw = plato.matrix_world.copy()
    piv_local = mw.inverted() @ PLATO_PIVOT
    plato.data.transform(Matrix.Translation(-piv_local))
    plato.matrix_world = mw @ Matrix.Translation(piv_local)
    plato["basculante"] = True
# el borde trasero del plato quedaba ~0.5 mm sobre el camino del huevo en los rieles: el huevo que arranca
# desde el pasador se trababa ahi. Se baja el plato 3 mm (y el eje de basculamiento con el)
if not plato.get("bajado_3mm"):
    plato.location.z -= 0.003; plato["bajado_3mm"] = True; PLATO_PIVOT.z -= 0.003
plato_basculante()
plato.rigid_body.kinematic = True
PLATO_RX0 = plato.rotation_euler.x
def plato_keys(f0):
    for f_, a_ in ((0, 0), (8, 0), (16, TILT), (30, TILT), (38, 0)):
        key_rot(plato, 0, f0+f_, PLATO_RX0 + math.radians(a_), 'BEZIER')
# boca de entrada abierta: las paredes del redireccionador cerca del plato (r < 9 cm) bajan al nivel del
# borde del plato; si no, para las bandejas izquierdas una pared queda justo delante de la salida del huevo
WALL_R, WALL_Z = 0.09, 0.1745
def abrir_boca_redireccionador():
    me = redir.data
    if me.get("boca_abierta"): return
    mw = redir.matrix_world
    for v in me.vertices:
        if v.co.xy.length < WALL_R and (mw @ v.co).z > WALL_Z:
            w = mw @ v.co; w.z = WALL_Z; v.co = mw.inverted() @ w
    me.update(); me["boca_abierta"] = True
if "boca" in argv: abrir_boca_redireccionador()      # probado: empeora (sin paredes no hay guia); desactivado
# ---------- redireccionador con ENTRADA CENTRAL (como el canal giratorio de Ovum1_3) ----------
# El eje pasa justo delante del borde del plato: el huevo cae siempre en la copa central, gire hacia donde gire,
# y sale rodando por la tolva (mas ancha hacia afuera, con pestanas). La malla original queda guardada.
AXIS = Vector((0.0, 0.0))                 # eje vertical del nuevo redireccionador (delante del plato)
CUP_R, CUP_Z = 0.032, 0.168               # radio de la copa y altura del piso en su borde trasero (bajo el labio del plato)
OUT_L, OUT_Z = 0.110, 0.147               # largo de la tolva y altura del piso en la salida (bordes de bandeja ~0.146)
WALL_X0 = 0.035                           # las paredes empiezan despues de la copa: entrada abierta desde cualquier lado
def z_piso(x): return CUP_Z - (CUP_Z - OUT_Z) * (x + CUP_R) / (OUT_L + CUP_R)   # todo el piso baja ~8.4 grados hacia la salida
def half_w(x): return 0.032 if x < 0.03 else 0.032 + (0.046 - 0.032) * (x - 0.03) / (OUT_L - 0.03)
def construir_redireccionador_central():
    if redir.data.get("entrada_central"): return
    old = redir.data; old.use_fake_user = True
    if "RedireccionadorBase_original" not in bpy.data.meshes: old.name = "RedireccionadorBase_original"
    bm = bmesh.new(); T = 0.003; WALL = 0.018; LIP = 0.008
    xs = [-CUP_R + i*(CUP_R+OUT_L)/24 for i in range(25)]
    # piso: copa semicircular atras + tolva hacia +X
    back = [Vector((CUP_R*math.cos(math.radians(a)), CUP_R*math.sin(math.radians(a)), z_piso(CUP_R*math.cos(math.radians(a))))) for a in range(90, 271, 15)]
    right = [Vector((x, -half_w(x), z_piso(x))) for x in xs if x >= 0]
    left = [Vector((x, half_w(x), z_piso(x))) for x in reversed(xs) if x >= 0]
    poly = back + right + left
    top = [bm.verts.new(v) for v in poly]; f = bm.faces.new(top)
    ex = bmesh.ops.extrude_face_region(bm, geom=[f])
    bmesh.ops.translate(bm, verts=[v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)], vec=(0, 0, -T))
    def wall(pts, h, side):
        vs = [bm.verts.new(p) for p in pts] + [bm.verts.new(p + Vector((0, 0, h))) for p in reversed(pts)]
        f = bm.faces.new(vs); ex = bmesh.ops.extrude_face_region(bm, geom=[f])
        bmesh.ops.translate(bm, verts=[v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)], vec=side*0.0025)
    # paredes laterales de la tolva (desde la copa hasta la salida) y pared baja de la copa
    for sgn in (-1, 1):
        pts = [Vector((x, sgn*half_w(x), z_piso(x))) for x in xs if x >= WALL_X0]
        wall(pts, WALL, Vector((0, sgn, 0)))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("Redireccionador_EntradaCentral"); bm.to_mesh(me); bm.free()
    for m in old.materials: me.materials.append(m)
    redir.data = me; me["entrada_central"] = True
    redir.location = (AXIS.x, AXIS.y, 0.0); redir.rotation_euler = (0, 0, 0)
    rb = redir.rigid_body
    rb.collision_shape = 'MESH'; rb.mesh_source = 'FINAL'; rb.kinematic = True
construir_redireccionador_central()
# superficie de baja friccion (recubrimiento PTFE): el huevo llega con el eje largo en X y hacia las bandejas
# inferiores tiene que DESLIZAR en esa direccion; con 0.35 se quedaba quieto en la copa
redir.rigid_body.friction = 0.15
# angulos del redireccionador medidos por simulacion (rango que funciona entre parentesis)
REDIR = {"Bandeja 4.001": 3.0,            # inferior derecha   (-6..12)
         "Bandeja 2.002": 45.0,           # superior derecha   (40..50)
         "Bandeja 2.001": 125.0,          # superior izquierda (110..140)
         "Bandeja 4.002": 180.0}          # inferior izquierda (174..186)
ORDER = list(REDIR)
TRAY_DROP = 0.010                         # bandejas 1 cm mas abajo: el borde quedaba 5 mm SOBRE la salida del redireccionador

NEGGS = len(eggs)
F = lambda c: P0 + c*TC                   # frame del empuje del ciclo c
sc.frame_end = F(NEGGS-1) + 70
rbw.point_cache.frame_end = sc.frame_end

# piezas en espejo (escala negativa): la colision de malla deja pasar los huevos. Se aplica la escala
# a la malla (misma forma, escala 1). Afectaba a las dos bandejas derechas.
fixed_scale = []
for o in sc.objects:
    if o.type == 'MESH' and o.rigid_body and o.matrix_world.determinant() < 0 and o.data.users == 1:
        S = Matrix.Diagonal(tuple(o.scale) + (1.0,))
        o.data.transform(S); o.data.flip_normals(); o.scale = (1, 1, 1); o.data.update(); fixed_scale.append(o.name)

# bandejas: bajar 1 cm (una sola vez)
lowered = []
for n in REDIR:
    t = bpy.data.objects[n]
    if not t.get("bajada_1cm"):
        t.location.z -= TRAY_DROP; t["bajada_1cm"] = True; lowered.append(n)

# huevos duplicados por accidente (copias exactas de Huevo_18 en el mismo lugar): fuera de la simulacion
dups = []
eggs = [o for o in eggs if o.rigid_body or "." in o.name]
for o in list(eggs):
    if "." in o.name:
        remove_rb(o); o.hide_viewport = True; o.hide_render = True; o.hide_set(True); dups.append(o.name); eggs.remove(o)
NEGGS = len(eggs)
sc.frame_end = F(NEGGS-1) + 90 + 2*TC        # dos ciclos extra: margen para huevos que llegan con retraso
rbw.point_cache.frame_end = sc.frame_end

# modulo de limpieza 1.5 cm mas atras: entre el ultimo cepillo y el plato no cabia un huevo (33 mm < 43 mm);
# el huevo que espera en el pasador quedaba sobre el cepillo girando, que lo ponia a lo largo de los rieles
LIMPIEZA_SHIFT = -0.015
moved = []
for n in ("Cepillo_Cama_1", "Cepillo_Cama_2", "Cepillo_Superior", "Limpieza_Carcasa", "Limpieza_Motor_Correa"):
    o = bpy.data.objects.get(n)
    if o and not o.get("limpieza_retrasada"):
        o.location.y += LIMPIEZA_SHIFT; o["limpieza_retrasada"] = True; moved.append(n)

# pasador retractil al final de los rieles (Cylinder.001, ya disenado): retiene al siguiente huevo
# 6 mm detras, fuera del barrido del gancho, y baja un instante para dejar pasar UNO al plato
pin = bpy.data.objects["Cylinder.001"]
pin.hide_set(False); pin.hide_viewport = False; pin.hide_render = False
if not pin.get("ajustado"):
    pin.location.y -= 0.023; pin["ajustado"] = True     # y=-0.099: el huevo que espera queda fuera del plato basculante
rbp = add_rb(pin, 'PASSIVE')
rbp.collision_shape = 'MESH'; rbp.friction, rbp.restitution = 0.9, 0.05
rbp.use_margin = True; rbp.collision_margin = MARGIN; rbp.kinematic = True
PIN_Z0 = pin.get("z0", pin.location.z); pin["z0"] = PIN_Z0
PIN_UP, PIN_DN = PIN_Z0 + 0.011, PIN_Z0 - 0.008      # punta a z=0.19 (retiene) / 0.167 (deja pasar)
PIN_Y = pin.matrix_world.translation.y

# posicion inicial: huevo 1 ya en el plato; la fila detras del pasador
TANA = math.tan(math.radians(4))
def ez(y): return 0.199 + (-0.075 - y)*TANA
ROT = Euler((0, math.pi/2, 0)).to_matrix().to_4x4()
# carga: huevo 1 en el plato, huevo 2 esperando en el pasador; el resto se carga a mano uno por ciclo
# (asi nunca hay fila dentro de los cepillos: empujarian huevos contra huevos detenidos)
eggs[0].animation_data_clear(); eggs[0].rigid_body.kinematic = False
eggs[0].matrix_world = Matrix.Translation((0.0, -0.054, 0.191)) @ ROT
eggs[1].animation_data_clear(); eggs[1].rigid_body.kinematic = False
# 1.5 mm de holgura con el pasador y 1 mm sobre los rieles: si arranca tocando algo, el primer paso de fisica lo dispara
y = PIN_Y - 0.0051 - 0.0215 - 0.0015; eggs[1].matrix_world = Matrix.Translation((0.0, y, ez(y) + 0.001)) @ ROT
DROP = Vector((0.0, -0.545, ez(-0.545) + 0.012))
HOLDS = [(x, yy, layer) for layer in range(2) for yy in (-0.555, -0.505, -0.455) for x in (-0.12, -0.07, 0.07, 0.12)]
def vtray_z(x, yy): return ez(yy) - 0.0245 + 0.006 + (abs(x)-0.03)*math.tan(math.radians(9))
LOAD_OFFSET = 76                         # carga en F(c)+76: llega (~F+93) con el pasador ya cerrado (F+83) y antes de que vuelva a abrir (F+127)
loaders = []
for i, o in enumerate(eggs[2:], start=2):
    x, yy, layer = HOLDS[i-2]
    hold = Vector((x, yy, vtray_z(x, yy) + 0.0225 + layer*0.045))
    fr = F(i-2) + LOAD_OFFSET
    o.animation_data_clear(); o.rotation_mode = 'XYZ'
    o.matrix_world = Matrix.Translation(hold) @ ROT
    rb = o.rigid_body
    rb.kinematic = True; rb.keyframe_insert("kinematic", frame=1)
    o.location = hold; o.keyframe_insert("location", frame=fr-10)
    o.location = DROP + Vector((0, 0, 0.03)); o.keyframe_insert("location", frame=fr-3)
    o.location = DROP; o.keyframe_insert("location", frame=fr)
    rb.keyframe_insert("kinematic", frame=fr)
    rb.kinematic = False; rb.keyframe_insert("kinematic", frame=fr+1)
    o.location = hold
    for fc in curves(o):
        if fc.data_path.startswith("rigid_body"):
            for kp in fc.keyframe_points: kp.interpolation = 'CONSTANT'
    loaders.append((o.name, fr))

# secuencia de bandejas (reproducible, las 4 reciben huevos)
random.seed(5)
seq = [c % 4 for c in range(NEGGS)]; random.shuffle(seq)

# gancho y plato basculante
gancho.animation_data_clear(); plato.animation_data_clear()
key_rot(gancho, 0, 1, math.radians(THETA_REST), 'BEZIER'); key_rot(plato, 0, 1, PLATO_RX0, 'BEZIER')
for c in range(NEGGS):
    gancho_keys(F(c)); plato_keys(F(c))
# redireccionador: se orienta mientras el huevo se pesa (el anterior ya salio)
redir.animation_data_clear()
prev = math.radians(REDIR[ORDER[seq[0]]])
key_rot(redir, 2, 1, prev)
for c in range(NEGGS):
    tgt = math.radians(REDIR[ORDER[seq[c]]])
    key_rot(redir, 2, F(c), prev); key_rot(redir, 2, F(c)+8, tgt); prev = tgt     # gira justo antes de bascular el plato
sc["Ovum_secuencia_bandejas"] = json.dumps([ORDER[k] for k in seq])
pin.animation_data_clear()
def kpin(f, z):
    pin.location.z = z; pin.keyframe_insert("location", index=2, frame=f)
kpin(1, PIN_UP)
for c in range(NEGGS):
    t0 = F(c) + CYCLE_GANCHO + 1             # gancho en reposo y plato plano: puede entrar el siguiente
    kpin(t0, PIN_UP); kpin(t0+2, PIN_DN); kpin(t0+28, PIN_DN); kpin(t0+30, PIN_UP)   # 26 frames abajo: margen para el huevo que parte desde quieto
for fc in curves(pin):
    for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
sc.frame_set(1)

report = {"sin_fisica_ocultos": removed, "limpieza_retrasada": moved, "escala_aplicada": fixed_scale, "duplicados_fuera": dups, "bandejas_bajadas": lowered, "frame_end": sc.frame_end, "secuencia": [ORDER[k] for k in seq]}
if "explorar3" in argv:
    out = {}
    for o in eggs:
        if o.name in rbw.collection.objects: rbw.collection.objects.unlink(o)
    test = eggs[0]; rbw.collection.objects.link(test)
    test.animation_data_clear(); test.rigid_body.kinematic = False; test.rotation_mode = 'XYZ'
    pin.animation_data_clear(); pin.location.z = PIN_UP
    # (1) tiempo de viaje desde la carga (y=-0.545) hasta el pasador
    gancho.animation_data_clear(); gancho.rotation_euler.x = math.radians(THETA_REST)
    test.matrix_world = Matrix.Translation((0.0, -0.545, ez(-0.545) + 0.012)) @ ROT
    reset_cache(); tt = None
    for f in range(1, 200):
        sc.frame_set(f)
        if tt is None and test.matrix_world.translation.y > -0.115: tt = f
    out["viaje_carga_a_pasador_frames"] = tt
    # (2) angulo del redireccionador por bandeja: huevo en el plato, empuje en el frame 40
    sweep = {}
    for tray, c0 in REDIR.items():
        for d in (-15, -10, -5, 0, 5, 10, 15):
            phi = c0 + d
            gancho.animation_data_clear()
            key_rot(gancho, 0, 1, math.radians(THETA_REST), 'LINEAR'); gancho_keys(40, THETA_REST)
            redir.animation_data_clear(); redir.rotation_euler.z = math.radians(phi)
            test.matrix_world = Matrix.Translation((0.0, -0.054, 0.194)) @ ROT
            reset_cache()
            for f in range(1, 141): sc.frame_set(f)
            t = tray_under(test.matrix_world.translation + Vector((0, 0, -0.022)))
            sweep.setdefault(tray, {})[phi] = t
    out["barrido_redireccionador"] = sweep
    print("RESULT " + json.dumps(out))
    raise SystemExit

if "explorar4" in argv:
    for o in eggs:
        if o.name in rbw.collection.objects: rbw.collection.objects.unlink(o)
    test = eggs[0]; rbw.collection.objects.link(test)
    test.animation_data_clear(); test.rigid_body.kinematic = False; test.rotation_mode = 'XYZ'
    pin.animation_data_clear(); pin.location.z = PIN_UP
    gancho.animation_data_clear()
    key_rot(gancho, 0, 1, math.radians(THETA_REST), 'LINEAR'); key_rot(gancho, 0, 40, math.radians(THETA_REST), 'LINEAR')
    gancho_keys(40, THETA_REST)
    redir.animation_data_clear(); redir.rotation_euler.z = 0.0
    test.matrix_world = Matrix.Translation((0.0, -0.054, 0.194)) @ ROT
    reset_cache(); rows = []
    for f in range(1, 101):
        sc.frame_set(f)
        if (f % 3 == 0 and f >= 36) or 40 <= f <= 70:
            pp = test.matrix_world.translation
            rows.append([f, [round(v, 3) for v in pp], round(math.degrees(gancho.rotation_euler.x)), tray_under(pp + Vector((0, 0, -0.022)))])
    print("RESULT " + json.dumps(rows))
    raise SystemExit

if "explorar5" in argv:
    out = {}
    for o in eggs:
        if o.name in rbw.collection.objects: rbw.collection.objects.unlink(o)
    test = eggs[0]; rbw.collection.objects.link(test)
    test.animation_data_clear(); test.rigid_body.kinematic = False; test.rotation_mode = 'XYZ'
    pin.animation_data_clear(); pin.location.z = PIN_UP
    for push in (-150, -180, -210, -240, -270):
        for hold in (8, 14):
            gancho.animation_data_clear()
            key_rot(gancho, 0, 1, math.radians(THETA_REST), 'LINEAR')
            key_rot(gancho, 0, 40, math.radians(THETA_REST), 'LINEAR')
            key_rot(gancho, 0, 50, math.radians(THETA_REST + push), 'BEZIER')
            key_rot(gancho, 0, 50+hold, math.radians(THETA_REST + push), 'BEZIER')
            key_rot(gancho, 0, 60+hold, math.radians(THETA_REST - 360), 'BEZIER')
            redir.animation_data_clear(); redir.rotation_euler.z = 0.0
            test.matrix_world = Matrix.Translation((0.0, -0.054, 0.194)) @ ROT
            reset_cache(); first = None; path = []
            for f in range(1, 141):
                sc.frame_set(f)
                pp = test.matrix_world.translation
                if first is None and pp.y > 0.0: first = f
                if f in (50, 50+hold, 60+hold, 80, 140): path.append([f] + [round(v, 3) for v in pp])
            out[f"{push}/h{hold}"] = {"cruza_y0": first, "path": path, "final": tray_under(test.matrix_world.translation + Vector((0, 0, -0.022)))}
    print("RESULT " + json.dumps(out))
    raise SystemExit

def extender_redireccionador(factor, r0=0.07):
    """alarga radialmente la boca del redireccionador (vertices a mas de r0 del eje), sin tocar el anillo del plato"""
    me = redir.data
    if me.get("extendido"): return
    for v in me.vertices:
        r = v.co.xy.length
        if r > r0:
            k = 1 + (factor - 1)*min(1.0, (r - r0)/0.03)
            v.co.x *= k; v.co.y *= k
    me.update(); me["extendido"] = factor

OUT_LOCAL_DEG = 111.0                    # direccion de la salida del redireccionador original (local)
def simetrizar_redireccionador():
    """deja el redireccionador simetrico respecto de su eje de salida: conserva la mitad que guia bien
    (la que recibe el huevo por el lado horario de la salida) y la refleja. Queda con la salida en +Y local."""
    me = redir.data
    if me.get("simetrico"): return
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(90 - OUT_LOCAL_DEG), 3, 'Z'))
    bmesh.ops.symmetrize(bm, input=bm.verts[:] + bm.edges[:] + bm.faces[:], direction='X', dist=0.0005)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free(); me.update(); me["simetrico"] = True

if "explorar6" in argv:
    out = {}
    if "simetrico" in argv:
        simetrizar_redireccionador()
        ws = [v.co for v in redir.data.vertices]
        out["chequeo_simetria"] = [round(min(v.x for v in ws), 4), round(max(v.x for v in ws), 4)]
    for a_ in argv:
        if a_.startswith("ext"): extender_redireccionador(float(a_[3:]))
    for o in eggs:
        if o.name in rbw.collection.objects: rbw.collection.objects.unlink(o)
    test = eggs[0]; rbw.collection.objects.link(test)
    test.animation_data_clear(); test.rigid_body.kinematic = False; test.rotation_mode = 'XYZ'
    pin.animation_data_clear(); pin.location.z = PIN_UP
    push = float(argv[argv.index("explorar6")+1]) if len(argv) > argv.index("explorar6")+1 else -210.0
    for phi in range(-100, 55, 5):
        gancho.animation_data_clear()
        key_rot(gancho, 0, 1, math.radians(THETA_REST), 'LINEAR'); key_rot(gancho, 0, 40, math.radians(THETA_REST), 'LINEAR')
        key_rot(gancho, 0, 50, math.radians(THETA_REST + push)); key_rot(gancho, 0, 58, math.radians(THETA_REST + push))
        key_rot(gancho, 0, 68, math.radians(THETA_REST - 360))
        redir.animation_data_clear(); redir.rotation_euler.z = math.radians(phi)
        test.matrix_world = Matrix.Translation((0.0, -0.054, 0.194)) @ ROT
        reset_cache()
        for f in range(1, 161): sc.frame_set(f)
        pp = test.matrix_world.translation
        out[phi] = [[round(v, 3) for v in pp], tray_under(pp + Vector((0, 0, -0.022)))]
    print("RESULT " + json.dumps(out))
    raise SystemExit

if "explorar8" in argv:
    out = {}
    for o in eggs:
        if o.name in rbw.collection.objects: rbw.collection.objects.unlink(o)
    test = eggs[0]; rbw.collection.objects.link(test)
    test.animation_data_clear(); test.rigid_body.kinematic = False; test.rotation_mode = 'XYZ'
    pin.animation_data_clear(); pin.location.z = PIN_UP
    targets = {"Bandeja 4.001": -60, "Bandeja 2.002": -25, "Bandeja 2.001": 30, "Bandeja 4.002": 47}
    for push_f in (16, 22):
        for push in (-200, -215):
            score = 0; detail = {}
            for tray, c0 in targets.items():
                for d in (-5, 0, 5):
                    phi = c0 + d
                    gancho.animation_data_clear()
                    key_rot(gancho, 0, 1, math.radians(THETA_REST), 'LINEAR'); key_rot(gancho, 0, 40, math.radians(THETA_REST), 'LINEAR')
                    key_rot(gancho, 0, 40+push_f, math.radians(THETA_REST + push)); key_rot(gancho, 0, 48+push_f, math.radians(THETA_REST + push))
                    key_rot(gancho, 0, 60+push_f, math.radians(THETA_REST - 360))
                    redir.animation_data_clear(); redir.rotation_euler.z = math.radians(phi)
                    test.matrix_world = Matrix.Translation((0.0, -0.054, 0.194)) @ ROT
                    reset_cache()
                    for f in range(1, 171): sc.frame_set(f)
                    t = tray_under(test.matrix_world.translation + Vector((0, 0, -0.022)))
                    detail[phi] = (t or "-").replace("Bandeja ", "B").replace("Piso_Colision", "piso").replace("RedireccionadorBase.001", "redir")
                    score += (t == tray)
            out[f"f{push_f}{push:+d}"] = {"aciertos": score, "detalle": detail}
    print("RESULT " + json.dumps(out))
    raise SystemExit

PLATO_PIVOT = Vector((0.0, -0.054 + 0.046, 0.177))   # borde delantero del plato (eje X)
def plato_basculante():
    """el plato pasa a girar sobre su borde delantero: se mueve el origen al eje sin mover la geometria"""
    if plato.get("basculante"): return
    mw = plato.matrix_world.copy()
    piv_local = mw.inverted() @ PLATO_PIVOT
    plato.data.transform(Matrix.Translation(-piv_local))
    plato.matrix_world = mw @ Matrix.Translation(piv_local)
    plato["basculante"] = True
    plato.rigid_body.kinematic = True

if "explorar9" in argv:
    out = {}
    plato_basculante()
    for o in eggs:
        if o.name in rbw.collection.objects: rbw.collection.objects.unlink(o)
    test = eggs[0]; rbw.collection.objects.link(test)
    test.animation_data_clear(); test.rigid_body.kinematic = False; test.rotation_mode = 'XYZ'
    pin.animation_data_clear(); pin.location.z = PIN_UP
    gancho.animation_data_clear(); gancho.rotation_euler.x = math.radians(THETA_REST)
    targets = {"Bandeja 4.001": -60, "Bandeja 2.002": -25, "Bandeja 2.001": 30, "Bandeja 4.002": 47}
    base_rx = plato.rotation_euler.x
    for tilt in (25, 35):
        score = 0; detail = {}
        for tray, c0 in targets.items():
            for d in (-5, 0, 5):
                phi = c0 + d
                plato.animation_data_clear()
                for f_, a_ in ((1, 0), (40, 0), (48, tilt), (60, tilt), (68, 0)):
                    key_rot(plato, 0, f_, base_rx + math.radians(a_), 'BEZIER')
                redir.animation_data_clear(); redir.rotation_euler.z = math.radians(phi)
                test.matrix_world = Matrix.Translation((0.0, -0.054, 0.194)) @ ROT
                reset_cache()
                for f in range(1, 171): sc.frame_set(f)
                t = tray_under(test.matrix_world.translation + Vector((0, 0, -0.022)))
                detail[phi] = (t or "-").replace("Bandeja ", "B").replace("Piso_Colision", "piso").replace("RedireccionadorBase.001", "redir")
                score += (t == tray)
        out[f"inclinacion {tilt}"] = {"aciertos": score, "detalle": detail}
    print("RESULT " + json.dumps(out))
    raise SystemExit

def donde(p):
    if abs(p.y + 0.054) < 0.03 and abs(p.x) < 0.03 and p.z > 0.17: return "plato"
    t = tray_under(p + Vector((0, 0, -0.022)))
    return (t or "-").replace("Bandeja ", "B").replace("Piso_Colision", "piso").replace("RedireccionadorBase.001", "redir")

if "explorar10" in argv:
    out = {}
    plato_basculante()
    for o in eggs:
        if o.name in rbw.collection.objects: rbw.collection.objects.unlink(o)
    test = eggs[0]; rbw.collection.objects.link(test)
    test.animation_data_clear(); test.rigid_body.kinematic = False; test.rotation_mode = 'XYZ'
    pin.animation_data_clear(); pin.location.z = PIN_UP
    targets = {"Bandeja 4.001": -60, "Bandeja 2.002": -25, "Bandeja 2.001": 30, "Bandeja 4.002": 47}
    base_rx = plato.rotation_euler.x
    if "afinar" in argv:
        targets = {"Bandeja 4.001": -60, "Bandeja 2.002": -25, "Bandeja 2.001": 30, "Bandeja 4.002": 60}
    if "izq_inf" in argv:
        targets = {"Bandeja 4.002": 70}
    deltas = (-10, -5, 0, 5, 10, 15) if "izq_inf" in argv else (-5, 0, 5)
    for opening in ((125,) if "izq_inf" in argv else (125, 140) if "afinar" in argv else (106, 125)):
        for tilt in ((-30,) if "izq_inf" in argv else (-30, -38) if "afinar" in argv else (-20, -30)):   # negativo: sube la parte trasera
            score = 0; detail = {}
            for tray, c0 in targets.items():
                for d in deltas:
                    phi = c0 + d
                    gancho.animation_data_clear()
                    for f_, a_ in ((1, 0), (40, 0), (50, opening), (80, opening), (92, 0)):
                        key_rot(gancho, 0, f_, math.radians(THETA_REST + a_), 'BEZIER')
                    plato.animation_data_clear()
                    for f_, a_ in ((1, 0), (48, 0), (56, tilt), (70, tilt), (78, 0)):
                        key_rot(plato, 0, f_, base_rx + math.radians(a_), 'BEZIER')
                    redir.animation_data_clear(); redir.rotation_euler.z = math.radians(phi)
                    test.matrix_world = Matrix.Translation((0.0, -0.054, 0.194)) @ ROT
                    reset_cache()
                    for f in range(1, 171): sc.frame_set(f)
                    r_ = donde(test.matrix_world.translation)
                    detail[phi] = r_; score += (r_ == tray.replace("Bandeja ", "B"))
            out[f"abre{opening}_inclina{tilt}"] = {"aciertos": score, "detalle": detail}
    print("RESULT " + json.dumps(out))
    raise SystemExit

if "explorar11" in argv:
    out = {}
    for o in eggs:
        if o.name in rbw.collection.objects: rbw.collection.objects.unlink(o)
    test = eggs[0]; rbw.collection.objects.link(test)
    test.animation_data_clear(); test.rigid_body.kinematic = False; test.rotation_mode = 'XYZ'
    pin.animation_data_clear(); pin.location.z = PIN_UP
    gancho.animation_data_clear(); plato.animation_data_clear()
    key_rot(gancho, 0, 1, math.radians(THETA_REST)); gancho_keys(40)
    key_rot(plato, 0, 1, PLATO_RX0); plato_keys(40)
    i11 = argv.index("explorar11")
    step = int(argv[i11+3]) if len(argv) > i11+3 and argv[i11+3].lstrip("-").isdigit() else 10
    for phi in range(int(argv[i11+1]), int(argv[i11+2]), step):
        redir.animation_data_clear(); redir.rotation_euler.z = math.radians(phi)
        test.matrix_world = Matrix.Translation((0.0, -0.054, 0.194)) @ ROT
        reset_cache()
        for f in range(1, 181): sc.frame_set(f)
        out[phi] = [donde(test.matrix_world.translation), [round(v, 3) for v in test.matrix_world.translation]]
    print("RESULT " + json.dumps(out))
    raise SystemExit

if "explorar7" in argv:
    for o in eggs:
        if o.name in rbw.collection.objects: rbw.collection.objects.unlink(o)
    test = eggs[0]; rbw.collection.objects.link(test)
    test.animation_data_clear(); test.rigid_body.kinematic = False; test.rotation_mode = 'XYZ'
    pin.animation_data_clear(); pin.location.z = PIN_UP
    phi = float(argv[argv.index("explorar7")+1])
    if "simetrico" in argv: simetrizar_redireccionador()
    gancho.animation_data_clear()
    key_rot(gancho, 0, 1, math.radians(THETA_REST), 'LINEAR'); key_rot(gancho, 0, 40, math.radians(THETA_REST), 'LINEAR')
    key_rot(gancho, 0, 50, math.radians(THETA_REST - 210)); key_rot(gancho, 0, 58, math.radians(THETA_REST - 210))
    key_rot(gancho, 0, 68, math.radians(THETA_REST - 360))
    redir.animation_data_clear(); redir.rotation_euler.z = math.radians(phi)
    test.matrix_world = Matrix.Translation((0.0, -0.054, 0.194)) @ ROT
    reset_cache(); rows = []
    for f in range(1, 80):
        sc.frame_set(f)
        pp = test.matrix_world.translation
        if f >= 40: rows.append([f, [round(v, 3) for v in pp], round(math.degrees(gancho.rotation_euler.x)), tray_under(pp + Vector((0, 0, -0.022)))])
    print("RESULT " + json.dumps(rows))
    raise SystemExit

if "prueba" in argv:
    for o in eggs:
        if o.name not in rbw.collection.objects: rbw.collection.objects.link(o)
    reset_cache()
    exit_info = {}
    egg_names = {o.name for o in eggs}
    for f in range(sc.frame_start, sc.frame_end + 1):
        sc.frame_set(f)
        for o in eggs:
            if o.name in exit_info: continue
            p = o.matrix_world.translation
            if p.y > -0.005 and p.z < 0.2:      # salio del plato hacia el redireccionador
                ang = math.degrees(redir.matrix_world.to_euler().z)
                exit_info[o.name] = (f, round(ang), min(REDIR, key=lambda n: abs(REDIR[n]-ang)))
    res = {}
    for o in eggs:
        r_ = donde(o.matrix_world.translation)
        res[o.name] = ("Bandeja " + r_[1:]) if r_.startswith("B") else r_
    from collections import Counter
    report["resultado"] = dict(Counter(res.values()))
    report["ok"] = sum(1 for n, (f, a, t) in exit_info.items() if res.get(n) == t)
    report["por_huevo"] = {n: [res[n], exit_info.get(n)] for n in res}
    sc.frame_set(1)
    bpy.ops.ptcache.free_bake_all()
if "save" in argv:
    bpy.ops.wm.save_mainfile(); report["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(report))
