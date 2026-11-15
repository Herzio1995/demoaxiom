"""Anima la cuna basculante y el canal giratorio de Ovum1_3 (distribucion en 4 bandejas, 2 niveles)
y los deja sincronizados con el escape (ciclo de 48 frames = 2 s por huevo).

Direcciones del canal medidas con rayos desde su salida (grados, eje +X = 0, antihorario):
  Bandeja 4.002 (inferior derecha) 5-35 -> 20     Bandeja 2.001 (superior derecha) 45-85 -> 65
  Bandeja 2     (superior izquierda) 95-135 -> 115  Bandeja 4.001 (inferior izquierda) 145-175 -> 160
Ciclo (f0 = 1 + 48*c, cuando el escape suelta un huevo):
  ~f0+29     el huevo llega a la cuna (medido con la fisica)
  f0+26..36  el canal gira hacia la bandeja del huevo (el anterior ya salio del canal)
  f0+30..40  pesaje + foto
  f0+40..43  la cuna bascula 30 grados hacia el centro; f0+47..51 vuelve

Uso: blender --background Ovum1_3.blend --python animar_mecanismo_ovum1_3.py -- [prueba] [save]
"""
import bpy, sys, json, math, random
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
sc = bpy.context.scene

TC = 48
TRAYS = {"Bandeja 4.002": 20.0, "Bandeja 2.001": 65.0, "Bandeja 2": 115.0, "Bandeja 4.001": 160.0}
ORDER = list(TRAYS)                       # categoria 0..3 -> bandeja
NEGGS = len([o for o in bpy.data.objects if o.name.startswith("Huevo_")])
NC = NEGGS                                 # un ciclo por huevo
F = lambda c: 1 + c*TC
sc.frame_end = F(NC-1) + 80                # alcanza para que el ultimo huevo llegue a su bandeja
if sc.rigidbody_world: sc.rigidbody_world.point_cache.frame_end = sc.frame_end

# piezas con escala negativa (copias en espejo): la colision de malla queda con las normales al reves y
# los huevos la atraviesan. Se aplica la escala a la malla (misma forma, escala 1).
fixed_scale = []
for o in sc.objects:
    if o.type == 'MESH' and o.rigid_body and any(v < 0 for v in o.scale) and o.data.users == 1:
        S = Matrix.Diagonal(tuple(o.scale) + (1.0,))
        o.data.transform(S)
        if o.scale[0]*o.scale[1]*o.scale[2] < 0: o.data.flip_normals()
        o.scale = (1, 1, 1); o.data.update(); fixed_scale.append(o.name)

canal = bpy.data.objects["Canal_Giratorio"]
cuna = bpy.data.objects["Cuna_Basculante"]

def key(o, idx, f, val, interp):
    o.rotation_euler[idx] = val; o.keyframe_insert("rotation_euler", index=idx, frame=f)
    ad = o.animation_data; act = ad.action
    try: curves = [fc for ly in act.layers for st in ly.strips for fc in st.channelbag(ad.action_slot).fcurves]
    except AttributeError: curves = list(act.fcurves)
    for fc in curves:
        if fc.data_path == "rotation_euler" and fc.array_index == idx:
            for kp in fc.keyframe_points:
                if int(round(kp.co.x)) == f: kp.interpolation = interp

# secuencia de categorias (reproducible); garantiza que las 4 bandejas reciban huevos
random.seed(5)
seq = [c % 4 for c in range(NC)]
random.shuffle(seq)

for o in (canal, cuna):
    o.animation_data_clear()
cuna.rotation_euler = (0, 0, 0)
canal.rotation_euler = (0, 0, math.radians(TRAYS[ORDER[seq[0]]]))
prev = canal.rotation_euler[2]
key(canal, 2, 1, prev, 'BEZIER')
key(cuna, 0, 1, 0.0, 'LINEAR')
for c in range(NC):
    f0 = F(c); target = math.radians(TRAYS[ORDER[seq[c]]])
    key(canal, 2, f0+26, prev, 'BEZIER'); key(canal, 2, f0+36, target, 'BEZIER'); prev = target
    key(cuna, 0, f0+40, 0.0, 'LINEAR'); key(cuna, 0, f0+43, math.radians(-30), 'LINEAR')
    key(cuna, 0, f0+47, math.radians(-30), 'LINEAR'); key(cuna, 0, f0+51, 0.0, 'LINEAR')
# escape: los pasadores tenian ciclos solo para 18 huevos; se rehacen para todos
pF, pR = bpy.data.objects["Pasador_Delantero"], bpy.data.objects["Pasador_Trasero"]
def zvals(o):
    ad = o.animation_data; act = ad.action
    try: curves = [fc for ly in act.layers for st in ly.strips for fc in st.channelbag(ad.action_slot).fcurves]
    except AttributeError: curves = list(act.fcurves)
    return [kp.co.y for fc in curves if fc.data_path == "location" and fc.array_index == 2 for kp in fc.keyframe_points]
PIN_UP = max(zvals(pF)); PIN_DN = min(zvals(pF))
for o in (pF, pR): o.animation_data_clear()
def kz(o, f, z):
    o.location.z = z; o.keyframe_insert("location", index=2, frame=f)
kz(pF, 1, PIN_UP); kz(pR, 1, PIN_DN)
for c in range(NC):
    f0 = F(c)
    kz(pF, f0, PIN_UP); kz(pF, f0+3, PIN_DN); kz(pF, f0+8, PIN_DN); kz(pF, f0+11, PIN_UP)
    kz(pR, f0, PIN_DN); kz(pR, f0+3, PIN_UP); kz(pR, f0+11, PIN_UP); kz(pR, f0+14, PIN_DN)
for o in (pF, pR):
    ad = o.animation_data; act = ad.action
    try: curves = [fc for ly in act.layers for st in ly.strips for fc in st.channelbag(ad.action_slot).fcurves]
    except AttributeError: curves = list(act.fcurves)
    for fc in curves:
        for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
# rieles de la limpieza solapados 1 cm con los tramos vecinos: si solo se tocan de punta, el motor
# de fisica "engancha" el huevo en el borde interno de la union cuando llega lento
rl = bpy.data.objects.get("Rieles_Limpieza")
if rl is not None and not rl.get("solapado"):
    import bmesh as _bm
    TANA = math.tan(math.radians(4))
    def zrail(y): return 0.199 + (-0.075 - y)*TANA - 0.0245
    YB0, YB1, OV = -0.255, -0.125, 0.01
    bm = _bm.new()
    for s_ in (-1, 1):
        p0 = Vector((s_*0.015, YB0-OV, zrail(YB0-OV))); p1 = Vector((s_*0.015, YB1+OV, zrail(YB1+OV))); d = p1 - p0
        g = _bm.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.004, radius2=0.004, depth=d.length)
        _bm.ops.rotate(bm, verts=g['verts'], cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix())
        _bm.ops.translate(bm, verts=g['verts'], vec=(p0+p1)/2)
    bm.to_mesh(rl.data); bm.free(); rl.data.update(); rl["solapado"] = True

# guias laterales dentro de la camara oscura (de la entrada hasta la cuna): sin ellas el huevo que
# rebota contra el tope o es empujado por el siguiente se va de lado y cae por el extremo de los rieles
if bpy.data.objects.get("Guias_Camara") is None:
    import bmesh as _bm
    TANA = math.tan(math.radians(4))
    def zrail(y): return 0.199 + (-0.075 - y)*TANA - 0.0245
    bm = _bm.new()
    for s_ in (-1, 1):
        y0, y1 = -0.112, -0.03
        z0a, z0b = zrail(y0)+0.008, zrail(-0.075)+0.004
        vs = [bm.verts.new(v) for v in ((s_*0.034, y0, z0a), (s_*0.034, y1, z0b), (s_*0.034, y1, z0b+0.03), (s_*0.034, y0, z0a+0.03))]
        f = bm.faces.new(vs)
        ex = _bm.ops.extrude_face_region(bm, geom=[f])
        _bm.ops.translate(bm, verts=[v for v in ex['geom'] if isinstance(v, _bm.types.BMVert)], vec=(s_*0.002, 0, 0))
    _bm.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("Guias_Camara"); bm.to_mesh(me); bm.free()
    if "Acero_Inox" in bpy.data.materials: me.materials.append(bpy.data.materials["Acero_Inox"])
    gc = bpy.data.objects.new("Guias_Camara", me)
    (bpy.data.collections.get("Inspeccion") or sc.collection).objects.link(gc)
    for ob in bpy.context.view_layer.objects: ob.select_set(False)
    gc.select_set(True); bpy.context.view_layer.objects.active = gc
    with bpy.context.temp_override(object=gc, active_object=gc, selected_objects=[gc], selected_editable_objects=[gc]):
        bpy.ops.rigidbody.object_add(type='PASSIVE')
    gc.rigid_body.collision_shape = 'MESH'; gc.rigid_body.friction, gc.rigid_body.restitution = 0.35, 0.1
    gc.rigid_body.use_margin = True; gc.rigid_body.collision_margin = 0.0005

# huevos con colision de CAPSULA (eje largo = Z local del huevo): la seccion queda perfectamente redonda.
# Con casco convexo de 36 caras el huevo lento se queda apoyado en una faceta (~10 grados) y no rueda en 4 grados.
for o in bpy.data.objects:
    if o.name.startswith("Huevo_") and o.rigid_body:
        o.rigid_body.collision_shape = 'CAPSULE'

# tope retractil frente a la cuna: el huevo llega con velocidad suficiente para saltar la varilla
# delantera (la cuna es poco profunda); el tope lo detiene y baja solo cuando la cuna bascula
import bmesh
TOPE_Y, TOPE_UP, TOPE_DN = -0.0175, 0.205, 0.163       # punta arriba / abajo (z de la punta)
tope = bpy.data.objects.get("Tope_Cuna")
if tope is None:
    me = bpy.data.meshes.new("Tope_Cuna"); bm = bmesh.new()
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.003, radius2=0.003, depth=0.05)
    bmesh.ops.translate(bm, verts=g['verts'], vec=(0, 0, -0.025))
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.0045, radius2=0.0045, depth=0.006)
    bmesh.ops.translate(bm, verts=g['verts'], vec=(0, 0, -0.003))
    bm.to_mesh(me); bm.free()
    for mname in ("Acero_Inox", "Caucho_Negro"):
        if mname in bpy.data.materials: me.materials.append(bpy.data.materials[mname])
    for poly in me.polygons: poly.material_index = 1 if poly.center.z > -0.006 else 0
    tope = bpy.data.objects.new("Tope_Cuna", me)
    (bpy.data.collections.get("Inspeccion") or sc.collection).objects.link(tope)
    tope.location = (0.0, TOPE_Y, TOPE_UP)
    for ob in bpy.context.view_layer.objects: ob.select_set(False)
    tope.select_set(True); bpy.context.view_layer.objects.active = tope
    with bpy.context.temp_override(object=tope, active_object=tope, selected_objects=[tope], selected_editable_objects=[tope]):
        bpy.ops.rigidbody.object_add(type='PASSIVE')
    rb = tope.rigid_body
    rb.collision_shape = 'MESH'; rb.friction, rb.restitution = 0.9, 0.05
    rb.use_margin = True; rb.collision_margin = 0.0005
tope.animation_data_clear()
kz(tope, 1, TOPE_UP)
for c in range(NC):
    f0 = F(c)
    kz(tope, f0+38, TOPE_UP); kz(tope, f0+40, TOPE_DN); kz(tope, f0+52, TOPE_DN); kz(tope, f0+55, TOPE_UP)
for o in (canal, cuna, pF, pR, tope):
    o.rigid_body.kinematic = True                  # pasivo animado: empuja y suelta los huevos
sc["Ovum_secuencia_bandejas"] = json.dumps([ORDER[k] for k in seq])

report = {"ciclos": NC, "frame_end": sc.frame_end, "escala_aplicada": fixed_scale, "secuencia": [ORDER[k] for k in seq]}
if "prueba" in argv:
    # simula todo y clasifica donde termina cada huevo
    boxes = {}
    for n in TRAYS:
        o = bpy.data.objects[n]; ws = [o.matrix_world @ v.co for v in o.data.vertices]
        boxes[n] = ([min(w[i] for w in ws) for i in range(3)], [max(w[i] for w in ws) for i in range(3)])
    eggs = sorted([o for o in bpy.data.objects if o.name.startswith("Huevo_")], key=lambda o: o.name)
    exit_info = {}
    for f in range(sc.frame_start, sc.frame_end + 1):
        sc.frame_set(f)
        for o in eggs:
            if o.name in exit_info: continue
            p = o.matrix_world.translation
            if p.y > -0.03 and math.hypot(p.x, p.y) > 0.095 and p.z < 0.16:
                ang = math.degrees(canal.matrix_world.to_euler().z) % 360
                exit_info[o.name] = (f, round(ang), min(TRAYS, key=lambda n: abs(TRAYS[n]-ang)))
    def inside(n, p, dz):
        lo, hi = boxes[n]
        return lo[0]-0.01 <= p.x <= hi[0]+0.01 and lo[1]-0.01 <= p.y <= hi[1]+0.01 and lo[2]+dz <= p.z <= hi[2]+0.05
    egg_names = {o.name for o in eggs}
    def where(p):
        # la superficie que sostiene al huevo: primer objeto (que no sea huevo) bajo su centro
        dg = bpy.context.evaluated_depsgraph_get(); origin = p.copy()
        for _ in range(8):
            ok, loc, nrm, idx, ob, m = sc.ray_cast(dg, origin, Vector((0, 0, -1)))
            if not ok: return "fuera (cayendo)"
            if ob.name in egg_names or ob.name == "Circle": origin = loc + Vector((0, 0, -0.0005)); continue
            if ob.name in TRAYS: return ob.name
            if ob.name == "Piso_Colision": return "fuera (piso)"
            return "en la maquina (%s) y=%.2f" % (ob.name, p.y)
        return "?"
    res = {o.name: where(o.matrix_world.translation) for o in eggs}
    report["salida_canal"] = exit_info
    report["ok"] = sum(1 for n, (f, a, t) in exit_info.items() if res.get(n) == t)
    report["atascados"] = {o.name: [round(v, 3) for v in o.matrix_world.translation] for o in eggs if res[o.name].startswith("en la")}
    from collections import Counter
    report["resultado"] = dict(Counter(res.values()))
    report["por_huevo"] = res
    sc.frame_set(sc.frame_start)
    bpy.ops.ptcache.free_bake_all()
if "save" in argv:
    bpy.ops.wm.save_mainfile(); report["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(report))
