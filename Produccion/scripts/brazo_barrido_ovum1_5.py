"""Ovum1_5: empujador como BRAZO DE BARRIDO con eje vertical (perpendicular a las varillas) + separador aparte.

Basado en el esquema "Opcion 3", con la salida HACIA ADELANTE (el redireccionador original solo alcanza
las 4 bandejas si el huevo le llega por delante):
  - Brazo de barrido (PETG): eje vertical fijo al bastidor, a la derecha de la balanza y a la altura del huevo.
    En reposo queda paralelo a las varillas, fuera del camino. Gira 90 grados en sentido horario: el
    empujador entra por detras del huevo y lo expulsa hacia adelante; luego vuelve.
  - Separador con actuador propio: pasador retractil entre las varillas, justo antes de la balanza.
    Retiene al huevo siguiente mientras se pesa y se barre; baja solo cuando el brazo ya volvio a reposo.
  - La balanza (plato) queda FIJA y desacoplada del motor.
  - El redireccionador (el original del usuario) gira hacia la bandeja de cada huevo.

Modos:  -- explorar a0 a1 paso   barrido de angulos del redireccionador (no guarda)
        -- prueba                 simulacion completa (no guarda)
        -- save                   configura y guarda
"""
import bpy, bmesh, sys, json, math, random
from mathutils import Vector, Matrix, Euler

argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
sc = bpy.context.scene; vl = bpy.context.view_layer; rbw = sc.rigidbody_world
MARGIN = 0.0005

def curves(o):
    ad = o.animation_data
    if not ad or not ad.action: return []
    try: return [fc for ly in ad.action.layers for st in ly.strips for fc in st.channelbag(ad.action_slot).fcurves]
    except AttributeError: return list(ad.action.fcurves)
def add_rb(o, kind):
    if o.rigid_body: return o.rigid_body
    for ob in vl.objects: ob.select_set(False)
    o.select_set(True); vl.objects.active = o
    with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o], selected_editable_objects=[o]):
        bpy.ops.rigidbody.object_add(type=kind)
    return o.rigid_body
def setup_rb(o, kind, fr, kin, shape='MESH'):
    rb = add_rb(o, kind); rb.collision_shape = shape; rb.mesh_source = 'FINAL'
    rb.friction, rb.restitution = fr, 0.05; rb.use_margin = True; rb.collision_margin = MARGIN; rb.kinematic = kin
    return rb
def key_rot(o, idx, f, val, interp='BEZIER'):
    o.rotation_euler[idx] = val; o.keyframe_insert("rotation_euler", index=idx, frame=f)
    for fc in curves(o):
        if fc.data_path == "rotation_euler" and fc.array_index == idx:
            for kp in fc.keyframe_points:
                if int(round(kp.co.x)) == f: kp.interpolation = interp
def reset_cache():
    rbw.point_cache.frame_start = rbw.point_cache.frame_start
    sc.frame_set(sc.frame_start)
def mat(name, col, metal=0.0, rough=0.5):
    m = bpy.data.materials.get(name)
    if m: return m
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1); b.inputs["Metallic"].default_value = metal; b.inputs["Roughness"].default_value = rough
    m.diffuse_color = (*col, 1); return m

eggs = sorted([o for o in bpy.data.objects if o.name.startswith("Huevo_") and "." not in o.name and o.rigid_body], key=lambda o: o.name)
plato = bpy.data.objects["PesadorBase.001"]
redir = bpy.data.objects["RedireccionadorBase.001"]

# ================= GEOMETRIA DEL BRAZO =================
A = Vector((0.070, -0.054))          # eje vertical: a la derecha del huevo y a su altura -> lo expulsa recto hacia adelante (~90 grados)
for a_ in argv:
    if a_.startswith("ay="): A.y = float(a_[3:])     # para explorar otras posiciones del eje
REST, SWEPT = 285.0, 150.0           # reposo: casi paralelo a las varillas, fuera del camino / barrido de 135 grados
ARM_L = 0.075                        # largo: cruza el huevo de lado a lado y pasa a ~8 mm del que espera en el pasador
ZP0, ZP1 = 0.180, 0.215              # cubre el centro del huevo (~0.193): empuje horizontal; pasa sobre la balanza (0.177)
ZTOP = 0.217

def build_brazo():
    bm = bmesh.new()
    def boxv(c, s, rotz=0.0):
        g = bmesh.ops.create_cube(bm, size=1)
        bmesh.ops.scale(bm, verts=g['verts'], vec=s)
        bmesh.ops.rotate(bm, verts=g['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(rotz, 3, 'Z'))
        bmesh.ops.translate(bm, verts=g['verts'], vec=c)
    def cyl(r, z0, z1, seg=24):
        g = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=z1-z0)
        bmesh.ops.translate(bm, verts=g['verts'], vec=(0, 0, (z0+z1)/2))
    cyl(0.009, ZP0, ZTOP+0.004)                                          # cubo sobre el eje
    boxv(((0.010+ARM_L)/2, -0.002, (ZP0+ZP1)/2), (ARM_L-0.010, 0.008, ZP1-ZP0))  # empujador de 8 mm (cara de empuje en -Y local)
    boxv((ARM_L, -0.007, (ZP0+ZP1)/2), (0.004, 0.014, ZP1-ZP0))          # gancho del extremo (abraza el huevo)
    me = bpy.data.meshes.new("Brazo_Barrido"); bm.to_mesh(me); bm.free()
    me.materials.append(mat("PETG_Naranja", (1.0, 0.33, 0.05), 0.0, 0.45))
    o = bpy.data.objects.new("Brazo_Barrido", me)
    sc.collection.objects.link(o)
    o.location = (A.x, A.y, 0.0); o.rotation_euler = (0, 0, math.radians(REST))
    return o

def build_servo():
    bm = bmesh.new()
    def boxv(c, s):
        g = bmesh.ops.create_cube(bm, size=1); bmesh.ops.scale(bm, verts=g['verts'], vec=s); bmesh.ops.translate(bm, verts=g['verts'], vec=c)
    boxv((A.x, A.y, 0.255), (0.042, 0.042, 0.04))                           # servo / motor paso a paso (invertido)
    me = bpy.data.meshes.new("Servo_Brazo"); bm.to_mesh(me); bm.free()
    me.materials.append(mat("Servo_Gris", (0.3, 0.32, 0.35), 0.5, 0.4))
    s = bpy.data.objects.new("Servo_Brazo", me); sc.collection.objects.link(s)
    bm = bmesh.new()
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.003, radius2=0.003, depth=0.03)
    bmesh.ops.translate(bm, verts=g['verts'], vec=(A.x, A.y, ZTOP + 0.012))
    PX, PY = 0.160, -0.060                                               # poste fuera del giro del redireccionador y de las bandejas
    boxv((PX, PY, 0.138), (0.012, 0.012, 0.276))                          # poste al piso
    d = Vector((A.x - PX, A.y - PY)); L = d.length
    g = bmesh.ops.create_cube(bm, size=1); bmesh.ops.scale(bm, verts=g['verts'], vec=(L + 0.02, 0.03, 0.006))      # mensula hasta el servo
    bmesh.ops.rotate(bm, verts=g['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(math.atan2(d.y, d.x), 3, 'Z'))
    bmesh.ops.translate(bm, verts=g['verts'], vec=((A.x + PX)/2, (A.y + PY)/2, 0.278))
    me = bpy.data.meshes.new("Soporte_Servo"); bm.to_mesh(me); bm.free()
    me.materials.append(mat("Acero_Inox_Brazo", (0.78, 0.79, 0.8), 1.0, 0.25))
    p = bpy.data.objects.new("Soporte_Servo", me); sc.collection.objects.link(p)
    return s, p

changes = []
# objetos ocultos (versiones anteriores del gancho, etc.) fuera de la simulacion: aunque no se vean, chocan
def remove_rb(o):
    for ob in vl.objects: ob.select_set(False)
    o.select_set(True); vl.objects.active = o
    with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o], selected_editable_objects=[o]):
        bpy.ops.rigidbody.object_remove()
for o in list(sc.objects):
    if o.rigid_body and (o.hide_get() or o.hide_viewport) and not o.name.endswith("_Colision"):
        remove_rb(o); changes.append("sin fisica (oculto): " + o.name)
# separador: pasador retractil entre las varillas, con su propio actuador (solenoide)
PIN_Y, PIN_UP, PIN_DN = -0.101, 0.195, 0.165   # punta arriba (retiene) / abajo (deja pasar)
def build_pin():
    bm = bmesh.new()
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.005, radius2=0.005, depth=0.045)
    bmesh.ops.translate(bm, verts=g['verts'], vec=(0, 0, -0.0225))
    me = bpy.data.meshes.new("Pasador_Separador"); bm.to_mesh(me); bm.free()
    me.materials.append(mat("Acero_Inox_Brazo", (0.78, 0.79, 0.8), 1.0, 0.25))
    o = bpy.data.objects.new("Pasador_Separador", me); sc.collection.objects.link(o)
    o.location = (0.0, PIN_Y, PIN_UP)
    bm = bmesh.new()
    g = bmesh.ops.create_cube(bm, size=1); bmesh.ops.scale(bm, verts=g['verts'], vec=(0.022, 0.022, 0.035))
    bmesh.ops.translate(bm, verts=g['verts'], vec=(0.0, PIN_Y, 0.11))
    me = bpy.data.meshes.new("Solenoide_Separador"); bm.to_mesh(me); bm.free()
    me.materials.append(mat("Servo_Gris", (0.3, 0.32, 0.35), 0.5, 0.4))
    sol = bpy.data.objects.new("Solenoide_Separador", me); sc.collection.objects.link(sol)
    return o
pin = bpy.data.objects.get("Pasador_Separador") or build_pin()
setup_rb(pin, 'PASSIVE', 0.9, True)

# reemplaza el esbozo del usuario (Empujador_separador) por el brazo completo
esb = bpy.data.objects.get("Empujador_separador")
if esb and not esb.get("reemplazado"):
    esb.hide_set(True); esb.hide_viewport = True; esb.hide_render = True; esb["reemplazado"] = True; changes.append("Empujador_separador oculto (reemplazado)")
brazo = bpy.data.objects.get("Brazo_Barrido") or build_brazo()
if not bpy.data.objects.get("Servo_Brazo"): build_servo(); changes.append("servo + soporte")
setup_rb(brazo, 'PASSIVE', 0.5, True)
# ---- alturas: el labio interior del redireccionador (0.177) quedaba a la altura del borde del plato y el huevo
# tenia que subir un escalon de 5-9 mm; un empuje horizontal lo atrapaba contra el labio. Se baja el redireccionador
# 1.2 cm (y las bandejas igual, para que sigan recibiendo) y la concavidad del plato pasa de ~7 a ~3.5 mm.
DROP_RD = 0.012
if not redir.get("bajado_12mm"):
    redir.location.z -= DROP_RD; redir["bajado_12mm"] = True; changes.append("redireccionador -1.2 cm")
for n in ("Bandeja 2.001", "Bandeja 2.002", "Bandeja 4.001", "Bandeja 4.002"):
    t = bpy.data.objects.get(n)
    if t and not t.get("bajada_12mm"):
        t.location.z -= DROP_RD; t["bajada_12mm"] = True; changes.append(n + " -1.2 cm")
if not plato.data.get("concavidad_suave"):
    mw = plato.matrix_world; mi = mw.inverted()
    top = max((mw @ v.co).z for v in plato.data.vertices)
    for v in plato.data.vertices:
        w = mw @ v.co
        if w.z > top - 0.0075 and w.z < top - 0.0002:
            w.z = top - (top - w.z)*0.5; v.co = mi @ w
    plato.data.update(); plato.data["concavidad_suave"] = True; changes.append("concavidad del plato ~3.5 mm")

# ---- rampas guia en la entrada de las bandejas inferiores: amplian 2 cm hacia el redireccionador su borde de
# entrada (que es corto y queda entre dos postes) y tapan el hueco por donde el huevo caia al piso
RAMP_EXT = 0.020
RAMP_EDGES = {   # borde de entrada de cada bandeja inferior (x, y), medido en el modelo
    "Bandeja 4.001": [(0.1182, -0.0375), (0.1054, -0.0182), (0.0957, -0.0005), (0.0837, 0.0149), (0.0780, 0.0222)],
    "Bandeja 4.002": [(-0.1134, -0.0375), (-0.1005, -0.0182), (-0.0908, -0.0005), (-0.0788, 0.0149), (-0.0731, 0.0222)],
}
RD_C = Vector((0.0, -0.0612))
def build_rampa(tray_name, pts):
    t = bpy.data.objects[tray_name]
    tz = [(t.matrix_world @ v.co).z for v in t.data.vertices if -0.04 < (t.matrix_world @ v.co).y < 0.025]
    z_edge = min(tz) + 0.0005                                  # altura del borde de entrada (ya bajado)
    z_in = max(z_edge + 0.002, redir.matrix_world.translation.z - 0.173 + 0.1514 - 0.0025)   # ~2.5 mm bajo la salida
    outer = [Vector((x, y, z_edge)) for x, y in pts]
    inner = []
    for x, y in pts:
        d = (RD_C - Vector((x, y))).normalized() * RAMP_EXT
        inner.append(Vector((x + d.x, y + d.y, z_in)))
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in outer + list(reversed(inner))]
    f = bm.faces.new(vs)
    ex = bmesh.ops.extrude_face_region(bm, geom=[f])
    bmesh.ops.translate(bm, verts=[v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)], vec=(0, 0, -0.003))
    for o_, i_ in ((outer[0], inner[0]),):     # pared lateral baja solo atras (la delantera atajaba el huevo)
        side = (o_ - i_).cross(Vector((0, 0, 1))).normalized() * 0.002
        q = [bm.verts.new(v) for v in (i_, o_, o_ + Vector((0, 0, 0.015)), i_ + Vector((0, 0, 0.015)))]
        f2 = bm.faces.new(q)
        ex2 = bmesh.ops.extrude_face_region(bm, geom=[f2])
        bmesh.ops.translate(bm, verts=[v for v in ex2['geom'] if isinstance(v, bmesh.types.BMVert)], vec=side)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    name = "Rampa_Guia_" + tray_name.split()[-1]
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.materials.append(mat("PETG_Gris", (0.75, 0.76, 0.78), 0.0, 0.4))
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o)
    setup_rb(o, 'PASSIVE', 0.35, False)
    return o
for tn, pts in RAMP_EDGES.items():
    nm = "Rampa_Guia_" + tn.split()[-1]
    if not bpy.data.objects.get(nm):
        build_rampa(tn, pts); changes.append("rampa guia en " + tn)
    else:
        setup_rb(bpy.data.objects[nm], 'PASSIVE', 0.35, False)

# balanza fija (desacoplada del motor)
plato.animation_data_clear()
if plato.get("basculante"): plato.rotation_euler.x = plato.get("rx0", plato.rotation_euler.x)
setup_rb(plato, 'PASSIVE', 0.9, False)
# el riel termina ~1.4 mm por debajo del plato: el huevo liberado no subia el escalon y esperaba al siguiente
if not plato.get("bajado_2_5mm"):
    plato.location.z -= 0.0025; plato["bajado_2_5mm"] = True; changes.append("plato bajado 2.5 mm (sin escalon riel-plato)")
# guias laterales bajas sobre el plato: centran el huevo que llega rodando en diagonal (si queda descentrado el brazo
# lo saca por el lado equivocado del redireccionador). Tope en z 0.1775, por debajo del empujador (z >= 0.180).
if not bpy.data.objects.get("Guias_Plato"):
    bm = bmesh.new()
    for sx in (-1, 1):
        g = bmesh.ops.create_cube(bm, size=1)
        bmesh.ops.scale(bm, verts=g['verts'], vec=(0.003, 0.062, 0.0145))
        bmesh.ops.translate(bm, verts=g['verts'], vec=(sx*0.030, -0.061, 0.17025))
    me = bpy.data.meshes.new("Guias_Plato"); bm.to_mesh(me); bm.free()
    me.materials.append(mat("PETG_Gris", (0.75, 0.76, 0.78), 0.0, 0.4))
    og = bpy.data.objects.new("Guias_Plato", me); sc.collection.objects.link(og)
    changes.append("guias laterales en el plato (x = +-3 cm)")
setup_rb(bpy.data.objects["Guias_Plato"], 'PASSIVE', 0.3, False)

# redireccionador: cuerpo fisico, gira a la bandeja de cada huevo
setup_rb(redir, 'PASSIVE', 0.12, True)   # PETG liso: con 0.35 el huevo se quedaba quieto en el canal (pendiente ~12 grados)
# ---- deflector: pared baja sobre el borde de la tolva, del lado contrario a la salida del canal (el canal apunta a +Y
# local). El brazo a veces lanza el huevo mas alla del borde frontal de la tolva; la pared lo ataja y lo devuelve al
# canal. Gira con el redireccionador (hijo). Tope en z 0.177: pasa por debajo del brazo (z >= 0.180).
DEF_A0, DEF_A1, DEF_TOP = -10.0, 55.0, 0.177
DEF_R, DEF_RISE = 0.100, 0.006
for a_ in argv:
    if a_.startswith("dro="): DEF_R = float(a_[4:])
    if a_.startswith("drise="): DEF_RISE = float(a_[6:])
def build_deflector():
    rz = redir.matrix_world.translation.z
    pts = [v.co for v in redir.data.vertices if v.co.xy.length > 0.03]
    R_OUT, T = DEF_R, 0.003
    bm = bmesh.new()
    def quadbox(c0, c1, c2, c3, dz):            # cara c0..c3 extruida dz (espesor)
        vs = [bm.verts.new(c) for c in (c0, c1, c2, c3)]
        f = bm.faces.new(vs); ex = bmesh.ops.extrude_face_region(bm, geom=[f])
        bmesh.ops.translate(bm, verts=[v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)], vec=dz)
    prev = None; first = None
    for k in range(int((DEF_A1 - DEF_A0) / 5) + 1):
        a_ = math.radians(DEF_A0 + 5*k); c, s_ = math.cos(a_), math.sin(a_)
        dang = lambda q: abs(math.atan2(math.sin(math.atan2(q.y, q.x) - a_), math.cos(math.atan2(q.y, q.x) - a_)))
        near = sorted(pts, key=dang)[:6]
        r_in = max(max(q.xy.length for q in near) - 0.004, 0.060); z_in = max(q.z for q in near) - 0.001
        z_out = z_in + DEF_RISE                                # piso inclinado hacia la tolva
        cur = (Vector((c*r_in, s_*r_in, z_in)), Vector((c*R_OUT, s_*R_OUT, z_out)))
        if prev:
            quadbox(prev[0], cur[0], cur[1], prev[1], (0, 0, -T))                       # piso
            zt = DEF_TOP - rz
            quadbox(prev[1], cur[1], Vector((cur[1].x, cur[1].y, zt)), Vector((prev[1].x, prev[1].y, zt)),
                    Vector((c, s_, 0)) * T)                                              # pared exterior
        else:
            first = cur
        prev = cur
    zt = DEF_TOP - rz; a0 = math.radians(DEF_A0); n0 = Vector((math.sin(a0), -math.cos(a0), 0)) * T
    quadbox(first[0], first[1], Vector((first[1].x, first[1].y, zt)), Vector((first[0].x, first[0].y, zt)), n0)  # tapa
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("Deflector_Redireccionador"); bm.to_mesh(me); bm.free()
    me.materials.append(mat("PETG_Gris", (0.75, 0.76, 0.78), 0.0, 0.4))
    o = bpy.data.objects.new("Deflector_Redireccionador", me); sc.collection.objects.link(o)
    o.parent = redir; o.matrix_parent_inverse = Matrix.Identity(4)
    return o
defl = bpy.data.objects.get("Deflector_Redireccionador")
if not defl:
    defl = build_deflector(); changes.append("deflector en el redireccionador")
setup_rb(defl, 'PASSIVE', 0.12, True)
for o in eggs:
    o.rigid_body.collision_shape = 'CAPSULE'

# ================= CICLO =================
TC = 84                           # 3.5 s por huevo (~1030 huevos/h)
P0 = 30
# ciclo (relativo a F):  -14..-4 el redireccionador gira | 0-30 barrido | 30-34 pausa | 34-54 vuelve
#                         56-76 el pasador baja y deja pasar al siguiente huevo | ~76-84 el huevo se asienta y se pesa
# El barrido es lento a proposito (~4 grados/frame): un brazo rapido "salta" dentro del huevo entre frames.
F = lambda c: P0 + c*TC
SWEEP_F, HOLD_F, BACK_F = 30, 4, 20
for a_ in argv:                       # pruebas: sw=frames de barrido, swept=angulo final
    if a_.startswith("sw="): SWEEP_F = int(a_[3:])
    if a_.startswith("swept="): SWEPT = float(a_[6:])
def brazo_keys(f0):
    for f_, a_ in ((0, REST), (SWEEP_F, SWEPT), (SWEEP_F+HOLD_F, SWEPT), (SWEEP_F+HOLD_F+BACK_F, REST)):
        key_rot(brazo, 2, f0+f_, math.radians(a_), 'BEZIER')
# angulos del redireccionador (se completan con el barrido 'explorar')
REDIR = {"Bandeja 4.001": float(sc.get("ov15_4001", -63)), "Bandeja 2.002": float(sc.get("ov15_2002", -20)),
         "Bandeja 2.001": float(sc.get("ov15_2001", 22)), "Bandeja 4.002": float(sc.get("ov15_4002", 51))}
for a_ in argv:                       # p. ej. r4002=51 para probar otro angulo sin editar
    if a_[:1] == "r" and "=" in a_ and a_[1:5].isdigit(): REDIR["Bandeja %s.%s" % (a_[1], a_[2:5])] = float(a_.split("=")[1])
ORDER = list(REDIR)

TANA = math.tan(math.radians(4))
def ez(y): return 0.199 + (-0.075 - y)*TANA
ROT = Euler((0, math.pi/2, 0)).to_matrix().to_4x4()
NEGGS = len(eggs)
sc.frame_end = F(NEGGS-1) + 90; rbw.point_cache.frame_end = sc.frame_end

# huevo 1 en la balanza; huevo 2 esperando en el pasador (con holgura); el resto se carga uno por ciclo
eggs[0].animation_data_clear(); eggs[0].rigid_body.kinematic = False
eggs[0].matrix_world = Matrix.Translation((0.0, -0.054, 0.193)) @ ROT
eggs[1].animation_data_clear(); eggs[1].rigid_body.kinematic = False
y2 = PIN_Y - 0.005 - 0.0215 - 0.0015; eggs[1].matrix_world = Matrix.Translation((0.0, y2, ez(y2) + 0.001)) @ ROT
DROP = Vector((0.0, -0.545, ez(-0.545) + 0.012))
HOLDS = [(x, yy, layer) for layer in range(2) for yy in (-0.555, -0.505, -0.455) for x in (-0.12, -0.07, 0.07, 0.12)]
def vtray_z(x, yy): return ez(yy) - 0.0245 + 0.006 + (abs(x)-0.03)*math.tan(math.radians(9))
LOAD_OFFSET = 64                  # sale de la carga en F(c)+64: llega al pasador ya cerrado (F+76) y antes de que vuelva a abrir (F+140)
for i, o in enumerate(eggs[2:], start=2):
    x, yy, layer = HOLDS[(i-2) % len(HOLDS)]
    hold = Vector((x, yy, vtray_z(x, yy) + 0.0225 + layer*0.045))
    fr = F(i-2) + LOAD_OFFSET
    o.animation_data_clear(); o.rotation_mode = 'XYZ'; o.matrix_world = Matrix.Translation(hold) @ ROT
    rb = o.rigid_body; rb.kinematic = True; rb.keyframe_insert("kinematic", frame=1)
    o.location = hold; o.keyframe_insert("location", frame=fr-10)
    o.location = DROP + Vector((0, 0, 0.03)); o.keyframe_insert("location", frame=fr-3)
    o.location = DROP; o.keyframe_insert("location", frame=fr)
    rb.keyframe_insert("kinematic", frame=fr); rb.kinematic = False; rb.keyframe_insert("kinematic", frame=fr+1)
    o.location = hold
    for fc in curves(o):
        if fc.data_path.startswith("rigid_body"):
            for kp in fc.keyframe_points: kp.interpolation = 'CONSTANT'

random.seed(5)
seq = [c % 4 for c in range(NEGGS)]; random.shuffle(seq)
brazo.animation_data_clear(); key_rot(brazo, 2, 1, math.radians(REST))
for c in range(NEGGS): brazo_keys(F(c))
redir.animation_data_clear()
prev = math.radians(REDIR[ORDER[seq[0]]]); key_rot(redir, 2, 1, prev)
for c in range(NEGGS):
    tgt = math.radians(REDIR[ORDER[seq[c]]])
    key_rot(redir, 2, F(c)-14, prev); key_rot(redir, 2, F(c)-4, tgt); prev = tgt   # gira con la balanza ocupada, antes del barrido
pin.animation_data_clear()
def kpin(f, z):
    pin.location.z = z; pin.keyframe_insert("location", index=2, frame=f)
kpin(1, PIN_UP)
for c in range(NEGGS):
    f0 = F(c)
    kpin(f0+54, PIN_UP); kpin(f0+56, PIN_DN); kpin(f0+74, PIN_DN); kpin(f0+76, PIN_UP)
for fc in curves(pin):
    for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
sc["Ovum_secuencia_bandejas"] = json.dumps([ORDER[k] for k in seq])
sc.frame_set(1)

def tray_under(p, depth=0.4):
    dg = bpy.context.evaluated_depsgraph_get(); origin = p.copy()
    for _ in range(8):
        ok, loc, nrm, idx, ob, m = sc.ray_cast(dg, origin, Vector((0, 0, -1)), distance=depth)
        if not ok: return None
        if ob.name.startswith("Huevo_") or not ob.rigid_body: origin = loc + Vector((0, 0, -0.0005)); continue
        return ob.name
def donde(p):
    if abs(p.y + 0.054) < 0.03 and abs(p.x) < 0.03 and p.z > 0.17: return "plato"
    t = tray_under(p + Vector((0, 0, -0.022)))
    return (t or "-").replace("Bandeja ", "B").replace("Piso_Colision", "piso").replace("RedireccionadorBase.001", "redir")

report = {"cambios": changes, "frame_end": sc.frame_end, "redir": REDIR}
if "explorar" in argv:
    i0 = argv.index("explorar"); a0, a1, st = (int(v) for v in argv[i0+1:i0+4])
    for o in eggs:
        if o.name in rbw.collection.objects: rbw.collection.objects.unlink(o)
    test = eggs[0]; rbw.collection.objects.link(test)
    pin.animation_data_clear(); pin.location.z = PIN_UP
    brazo.animation_data_clear(); key_rot(brazo, 2, 1, math.radians(REST)); brazo_keys(40)
    out = {}
    for phi in range(a0, a1, st):
        redir.animation_data_clear(); redir.rotation_euler.z = math.radians(phi)
        test.matrix_world = Matrix.Translation((0.0, -0.054, 0.193)) @ ROT
        reset_cache()
        for f in range(1, 171): sc.frame_set(f)
        out[phi] = donde(test.matrix_world.translation)
    report["barrido"] = out
if "prueba" in argv:
    reset_cache(); exit_info = {}
    for f in range(sc.frame_start, sc.frame_end + 1):
        sc.frame_set(f)
        for o in eggs:
            p = o.matrix_world.translation
            if o.name not in exit_info and (p.y > -0.02 or abs(p.x) > 0.045) and p.z < 0.2 and p.y > -0.1:
                exit_info[o.name] = (f, round(math.degrees(redir.matrix_world.to_euler().z)))
    res = {o.name: donde(o.matrix_world.translation) for o in eggs}
    inv = {round(v): k.replace("Bandeja ", "B") for k, v in REDIR.items()}
    ok = sum(1 for n, (f, a) in exit_info.items() if inv.get(a) == res.get(n))
    from collections import Counter
    report.update({"resultado": dict(Counter(res.values())), "correctos": ok, "por_huevo": {n: [res[n], exit_info.get(n)] for n in res}})
    sc.frame_set(1); bpy.ops.ptcache.free_bake_all()
if "save" in argv:
    bpy.ops.wm.save_mainfile(); report["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(report))
