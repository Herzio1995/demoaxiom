"""Clasificadora SH1800A MEJORADA (Tilinka Hardworks) - parte del modelo SH1800A y cambia su mecanismo.

Se conserva: abanico de 5 bandejas inclinadas, divisores, faldones, panel y medidas en planta.
Se cambia el mecanismo central por uno mas simple y por gravedad:
  * Canaleta de rieles inclinada 4 grados: los huevos ruedan acostados (antes se deslizaban de punta).
  * Escape de 2 pasadores con una leva (1 motor): sale exactamente UN huevo por ciclo.
  * Modulo de limpieza en la canaleta: cama de 2 cepillos + cepillo superior (empujan hacia el centro).
  * Camara oscura de inspeccion: cuna basculante sobre celda de carga + LED inferior + camara
    (pesaje y ovoscopia en la misma parada de ~0.5 s).
  * Canal giratorio (1 motor paso a paso) en lugar de la horquilla/paleta: se orienta hacia la
    bandeja MIENTRAS el huevo se pesa; el huevo baja rodando por gravedad. Sin empujes.
  * Rampa y caja de rechazo (fecundados / sucios / fisurados) en el sector frontal libre.
Uso: blender --background --factory-startup --python build_sh1800a_mejorada.py -- OUT.blend PREVIEW_PREFIX
"""
import bpy, bmesh, math, sys, json, random
from mathutils import Vector, Matrix, Euler

argv = sys.argv[sys.argv.index("--")+1:]
OUT, PREV = argv[0], argv[1]

# ---------- escena limpia ----------
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
    for d in list(coll): coll.remove(d)
for c in list(bpy.data.collections): bpy.data.collections.remove(c)
sc = bpy.context.scene
sc.unit_settings.system = 'METRIC'; sc.unit_settings.length_unit = 'CENTIMETERS'
sc.render.fps = 24

# ---------- parametros (ficha SH1800A: 106 x 93 x 20 cm, 5 bandejas, 1800 huevos/h) ----------
ANG  = [-10, 30, 70, 110, 150, 190]          # 6 lineas radiales -> 5 bandejas de 40 grados
HALF = math.radians(20)
RV   = 1.06 / (2*math.cos(math.radians(10))) # radio a los vertices => ancho 106 cm
R0   = 0.085                                 # borde interior de las bandejas
ZIN, ZOUT = 0.12, 0.065                      # bandejas inclinadas hacia afuera (los huevos ruedan al borde)
FOOT = 0.015                                 # altura de las patas de caucho
YBACK = RV*math.sin(math.radians(70))
YFRONT = -(0.93 - YBACK)                     # => fondo total 93 cm
T, HD, TD, TR = 0.003, 0.025, 0.004, 0.015   # espesor bandeja, alto divisor, espesor divisor, espesor tope
EGG_L, EGG_B = 0.057, 0.043; ER = EGG_B/2
ZC = 0.15                                    # altura del centro del huevo en la copa de pesaje

main = bpy.data.collections.new("Clasificadora_SH1800A_Mejorada"); sc.collection.children.link(main)
def sub(n):
    c = bpy.data.collections.new(n); main.children.link(c); return c
cB, cE, cC, cA, cH = [sub(n) for n in ("Bandejas", "Estructura", "Canaleta", "Mecanismo_Central", "Huevos")]
root = bpy.data.objects.new("SH1800A_Raiz", None); main.objects.link(root); root.empty_display_size = 0.15

def mat(name, col, metal=0.0, rough=0.5, emit=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1); b.inputs["Metallic"].default_value = metal; b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*col, 1); b.inputs["Emission Strength"].default_value = emit
    m.diffuse_color = (*col, 1); m.metallic = metal; m.roughness = rough
    return m
mat("Naranja_Exergy", (1.0, 0.27, 0.02), 0.0, 0.3)
mat("Bandeja_Blanca", (0.93, 0.93, 0.92), 0.0, 0.35)
mat("Caucho_Negro", (0.02, 0.02, 0.02), 0.0, 0.8)
mat("Acero_Inox", (0.78, 0.79, 0.8), 1.0, 0.22)
mat("Aletas_Blancas", (0.97, 0.97, 0.97), 0.0, 0.5)
mat("Laton", (0.85, 0.65, 0.25), 1.0, 0.3)
mat("Motor_Negro", (0.06, 0.06, 0.07), 0.3, 0.45)
mat("LED_Rojo", (1.0, 0.05, 0.03), 0.0, 0.3, emit=4)
mat("LED_Verde", (0.1, 1.0, 0.2), 0.0, 0.3, emit=4)
mat("Interruptor_Rojo", (0.8, 0.05, 0.05), 0.0, 0.4)
mat("Cascara_Huevo", (0.72, 0.42, 0.24), 0.0, 0.6)
M = bpy.data.materials

def mk(name, bm, coll, mats, loc=(0, 0, 0)):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for m in mats: me.materials.append(M[m])
    o = bpy.data.objects.new(name, me); coll.objects.link(o); o.parent = root; o.location = loc
    return o
def setmat(verts, mi):
    for f in {f for v in verts for f in v.link_faces}: f.material_index = mi
def prism(bm, pts, d, mi=0):
    vs = [bm.verts.new(p) for p in pts]
    f = bm.faces.new(vs)
    ex = bmesh.ops.extrude_face_region(bm, geom=[f])
    nv = [v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=nv, vec=d)
    setmat(vs + nv, mi); return vs + nv
def box(bm, c, s, mi=0):
    g = bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.scale(bm, verts=g['verts'], vec=s); bmesh.ops.translate(bm, verts=g['verts'], vec=c)
    setmat(g['verts'], mi); return g['verts']
def cylZ(bm, r, z0, z1, seg=24, c=(0, 0, 0), mi=0):
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=z1-z0)
    bmesh.ops.translate(bm, verts=g['verts'], vec=(c[0], c[1], (z0+z1)/2))
    setmat(g['verts'], mi); return g['verts']
def xform(bm, verts, rot=None, loc=None):
    if rot is not None: bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=rot)
    if loc is not None: bmesh.ops.translate(bm, verts=verts, vec=loc)
def pol(r, a, z): a = math.radians(a); return Vector((r*math.cos(a), r*math.sin(a), z))

# plano de cada bandeja: z lineal con la distancia a lo largo de la bisectriz
def tray_dir(i): return pol(1, (ANG[i]+ANG[i+1])/2, 0)
def tray_z(p, i):
    d = p.dot(tray_dir(i)); d0 = R0*math.cos(HALF); d1 = RV*math.cos(HALF)
    return ZIN + (ZOUT-ZIN)*(d-d0)/(d1-d0)

# ================= ESTRUCTURA =================
# 5 bandejas blancas
for i in range(5):
    a0, a1 = ANG[i], ANG[i+1]
    bm = bmesh.new(); prism(bm, [pol(R0, a0, ZIN), pol(RV, a0, ZOUT), pol(RV, a1, ZOUT), pol(R0, a1, ZIN)], (0, 0, -T))
    mk(f"Bandeja_{i+1}", bm, cB, ["Bandeja_Blanca"])

# divisores naranja con canto negro + paneles laterales hasta las patas
RD0, RD1 = 0.15, 0.21
def zl(r): return ZIN + (ZOUT-ZIN)*(r-R0)/(RV-R0)     # altura de la bandeja sobre una linea radial
bmO = bmesh.new(); bmK = bmesh.new()
for i, a in enumerate(ANG):
    n = pol(1, a+90, 0)*(TD/2)
    if i == 5:        # panel lateral izquierdo: de punta a punta, hasta las patas
        pts = [pol(R0, a, FOOT), pol(RV, a, FOOT), pol(RV, a, ZOUT+HD-0.004), pol(R0, a, ZIN+HD-0.004)]
        r_cap = R0
    else:             # divisores y panel derecho: nacen en r=0.15 (deja girar el canal hacia el rechazo)
        zb0, zb1 = (FOOT, FOOT) if i == 0 else (zl(RD0)-T, ZOUT-T)
        pts = [pol(RD0, a, zb0), pol(RV, a, zb1), pol(RV, a, ZOUT+HD-0.004)]
        for k in range(0, 7):
            r_ = RD1 - (RD1-RD0)*k/6
            pts.append(pol(r_, a, zl(r_) + 0.0015 + (HD-0.0055)*math.sin(math.pi/2*(r_-RD0)/(RD1-RD0))))
        r_cap = RD1
    prism(bmO, [p-n for p in pts], n*2)
    pts = [pol(r_cap, a, zl(r_cap)+HD-0.004), pol(RV, a, ZOUT+HD-0.004), pol(RV, a, ZOUT+HD), pol(r_cap, a, zl(r_cap)+HD)]
    prism(bmK, [p-n*1.2 for p in pts], n*2.4)
mk("Divisores", bmO, cB, ["Naranja_Exergy"])
mk("Divisores_Canto", bmK, cB, ["Caucho_Negro"])

# borde exterior: faldon naranja + tope de caucho negro
bmS = bmesh.new(); bmR = bmesh.new()
for i in range(5):
    p0, p1 = pol(RV, ANG[i], 0), pol(RV, ANG[i+1], 0)
    inward = -tray_dir(i)*TR
    prism(bmS, [p0+Vector((0, 0, FOOT)), p1+Vector((0, 0, FOOT)), p1+Vector((0, 0, ZOUT-T)), p0+Vector((0, 0, ZOUT-T))], inward)
    prism(bmR, [p0+Vector((0, 0, ZOUT-T)), p1+Vector((0, 0, ZOUT-T)), p1+Vector((0, 0, ZOUT+HD)), p0+Vector((0, 0, ZOUT+HD))], inward)
mk("Faldon_Exterior", bmS, cE, ["Naranja_Exergy"])
mk("Tope_Caucho", bmR, cE, ["Caucho_Negro"])

# patas de caucho
bm = bmesh.new()
for a in ANG:
    for r in (RV-0.03, 0.2):
        p = pol(r, a, 0); cylZ(bm, 0.022, 0, FOOT, 32, (p.x, p.y))
mk("Patas_Caucho", bm, cE, ["Caucho_Negro"])

# soporte interior bajo las bandejas (chapa en abanico + postes)
bm = bmesh.new()
zr = ZIN + (ZOUT-ZIN)*(0.2-R0)/(RV-R0) - T - 0.006   # bajo la bandeja en r=0.2
pts = [pol(R0, a, zr) for a in range(-10, 191, 10)] + [pol(0.2, a, zr) for a in range(190, -11, -10)]
prism(bm, pts, (0, 0, 0.004))
for a in (10, 90, 170):
    p = pol(0.15, a, 0); box(bm, (p.x, p.y, (FOOT+zr)/2), (0.02, 0.02, zr-FOOT))
mk("Soporte_Interior", bm, cE, ["Naranja_Exergy"])

# placa base central naranja (con el logo en el video) + escuadras laterales
bm = bmesh.new()
ZP = 0.05
pent = [Vector((x, y, ZP)) for x, y in ((-0.1, 0.06), (0.1, 0.06), (0.12, -0.08), (0.0, -0.16), (-0.12, -0.08))]
prism(bm, pent, (0, 0, 0.004))
for s in (-1, 1):
    prism(bm, [Vector((s*0.1, 0.06, ZP)), Vector((s*0.12, -0.08, ZP)), Vector((s*0.12, -0.08, FOOT)), Vector((s*0.1, 0.06, FOOT))], (-s*0.003, 0, 0))
mk("Placa_Base", bm, cE, ["Naranja_Exergy"])

# LEDs, boton, toma IEC con interruptor y cable (panel lateral derecho, como en el video)
a = math.radians(-10); u = Vector((math.cos(a), math.sin(a), 0)); nrm = Vector((math.sin(a), -math.cos(a), 0))
rotP = Matrix.Rotation(a, 3, 'Z') @ Matrix.Rotation(math.radians(90), 3, 'X')
def panel_cyl(name, r, h, along, z, matname):
    bm = bmesh.new(); v = cylZ(bm, r, 0, h, 20)
    xform(bm, v, rotP, u*along + nrm*(TD/2) + Vector((0, 0, z)))
    return mk(name, bm, cE, [matname])
panel_cyl("LED_Rojo", 0.004, 0.004, RV-0.26, 0.05, "LED_Rojo")
panel_cyl("LED_Verde", 0.004, 0.004, RV-0.225, 0.05, "LED_Verde")
panel_cyl("Boton", 0.006, 0.005, RV-0.19, 0.05, "Acero_Inox")
bm = bmesh.new()
v = box(bm, (0, -0.006, 0), (0.045, 0.012, 0.035)); xform(bm, v, Matrix.Rotation(a, 3, 'Z'), u*(RV-0.06)+nrm*(TD/2)+Vector((0, 0, 0.042)))
v = box(bm, (0, -0.013, 0.008), (0.012, 0.004, 0.012), mi=1); xform(bm, v, Matrix.Rotation(a, 3, 'Z'), u*(RV-0.06)+nrm*(TD/2)+Vector((0, 0, 0.042)))
mk("Toma_IEC", bm, cE, ["Caucho_Negro", "Interruptor_Rojo"])
cu = bpy.data.curves.new("Cable_Alimentacion", 'CURVE'); cu.dimensions = '3D'
cu.bevel_depth = 0.004; cu.bevel_resolution = 3
sp = cu.splines.new('BEZIER'); sp.bezier_points.add(2)
p0 = u*(RV-0.06)+nrm*0.02+Vector((0, 0, 0.035))
for bp, co in zip(sp.bezier_points, (p0, p0+nrm*0.07+Vector((0, 0, -0.03)), p0+nrm*0.2+u*0.12+Vector((0, 0, -0.031)))):
    bp.co = co; bp.handle_left_type = bp.handle_right_type = 'AUTO'
cu.materials.append(M["Caucho_Negro"])
cab = bpy.data.objects.new("Cable_Alimentacion", cu); cE.objects.link(cab); cab.parent = root

# ================= MEJORAS: ALIMENTACION POR GRAVEDAD, LIMPIEZA, OVOSCOPIA, CANAL GIRATORIO =================
mat("LED_Retroiluminacion", (1.0, 0.85, 0.6), 0.0, 0.3, emit=0.001)
mat("Cerdas_Nylon", (0.95, 0.75, 0.15), 0.0, 0.6)
mat("Nucleo_Cepillo", (0.15, 0.15, 0.16), 0.0, 0.4)
mat("Negro_Mate", (0.03, 0.03, 0.035), 0.0, 0.9)
mat("Lente_Vidrio", (0.05, 0.08, 0.12), 0.0, 0.05)
mat("Celda_Carga", (0.7, 0.72, 0.75), 0.8, 0.3)
mat("Espuma_Gris", (0.45, 0.47, 0.5), 0.0, 0.9)
mat("HDPE_Blanco", (0.93, 0.93, 0.92), 0.0, 0.4)
led = M["LED_Retroiluminacion"]
cL = sub("Limpieza"); cI = sub("Inspeccion")

def cyl(bm, p0, p1, r, seg=24, mi=0, r2=None):
    p0, p1 = Vector(p0), Vector(p1); d = p1 - p0
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=d.length)
    q = Vector((0, 0, 1)).rotation_difference(d.normalized())
    bmesh.ops.rotate(bm, verts=g['verts'], cent=(0, 0, 0), matrix=q.to_matrix())
    bmesh.ops.translate(bm, verts=g['verts'], vec=(p0+p1)/2)
    setmat(g['verts'], mi); return g['verts']
def brush(name, coll, r_core, r_tip, length, rows_dy=0.006, ntuft=20, axle=0.0):
    """cepillo cilindrico, eje en Y local (origen en el eje)"""
    bm = bmesh.new()
    cyl(bm, (0, -length/2, 0), (0, length/2, 0), r_core, 32, mi=0)
    if axle: cyl(bm, (0, -axle, 0), (0, axle, 0), 0.004, 12, mi=0)
    for i in range(int(length/rows_dy)):
        y = -length/2 + rows_dy/2 + i*rows_dy
        for k in range(ntuft):
            a = 2*math.pi*(k + 0.5*(i % 2))/ntuft
            d = Vector((math.cos(a), 0, math.sin(a)))
            cyl(bm, d*(r_core-0.001) + Vector((0, y, 0)), d*r_tip + Vector((0, y, 0)), 0.0013, 5, mi=1, r2=0.0018)
    return mk(name, bm, coll, ["Nucleo_Cepillo", "Cerdas_Nylon"])
def key_rot(o, axis, f, val):
    o.rotation_euler[axis] = val; o.keyframe_insert("rotation_euler", index=axis, frame=f)
def key_loc(o, axis, f, val):
    o.location[axis] = val; o.keyframe_insert("location", index=axis, frame=f)
def fcurves_of(idb):
    ad = idb.animation_data; act = ad.action
    try:
        return [fc for ly in act.layers for st in ly.strips for fc in st.channelbag(ad.action_slot).fcurves]
    except AttributeError:
        return list(act.fcurves)
def linear_forever(o):
    for fc in fcurves_of(o):
        for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
        fc.extrapolation = 'LINEAR'

# ---------- niveles del recorrido (todo baja por gravedad) ----------
TANA = math.tan(math.radians(4))       # pendiente de la canaleta
Y_CR = -0.045                          # cuna de inspeccion (antes del centro)
Z_CR = 0.195                           # centro del huevo en la cuna
Y_END = -0.075                         # fin de los rieles (dentro de la camara oscura)
Y_FRONT = -0.56                        # inicio de la bandeja de carga
EH = 0.0245                            # centro del huevo sobre el eje de los rieles
def ezc(y): return Z_CR + 0.004 + (Y_END - y)*TANA       # altura del huevo rodando por la canaleta
def zrail(y): return ezc(y) - EH
ZS0, TANB = 0.165, 0.2                 # canal giratorio: centro del huevo en el eje y pendiente (11 grados)
def zsp(r): return ZS0 - r*TANB
ROUT = 0.105                           # salida del canal (sobre los labios de las bandejas)
PIN_F = -0.265; PIN_R = PIN_F - 0.0465 # pasadores del escape
YB0, YB1, YBT = -0.255, -0.125, -0.19  # modulo de limpieza
REJ = -50.0                            # direccion de la rampa de rechazo

# ---------- canaleta: rieles inox + guias + bandeja de carga en V ----------
bm = bmesh.new()
for ya, yb in ((Y_FRONT, YB0), (YB1, Y_END)):
    for s in (-1, 1):
        cyl(bm, (s*0.015, ya, zrail(ya)), (s*0.015, yb, zrail(yb)), 0.004, 16)
mk("Rieles_Canaleta", bm, cC, ["Acero_Inox"])
bm = bmesh.new()
for s in (-1, 1):
    for ya, yb in ((-0.42, YB0+0.005), (YB1-0.005, -0.11)):
        p0 = Vector((s*0.034, ya, zrail(ya)+0.008)); p1 = Vector((s*0.034, yb, zrail(yb)+0.008))
        prism(bm, [p0, p1, p1+Vector((0, 0, 0.032)), p0+Vector((0, 0, 0.032))], (s*0.002, 0, 0))
mk("Guias_Canaleta", bm, cC, ["Acero_Inox"])
TV = math.radians(9)
def vz(y, x): return zrail(y) + 0.002 + (abs(x)-0.03)*math.tan(TV)
bm = bmesh.new()
ya, yb = Y_FRONT-0.01, -0.42
for s in (-1, 1):
    pts = [Vector((s*0.03, ya, vz(ya, 0.03))), Vector((s*0.03, yb, vz(yb, 0.03))), Vector((s*0.05, yb, vz(yb, 0.05))),
           Vector((s*0.16, yb-0.06, vz(yb-0.06, 0.16))), Vector((s*0.16, ya, vz(ya, 0.16)))]
    prism(bm, pts, (0, 0, -0.004), mi=0)
    prism(bm, [Vector((s*0.16, ya, vz(ya, 0.16))), Vector((s*0.16, yb-0.06, vz(yb-0.06, 0.16))), Vector((s*0.05, yb, vz(yb, 0.05))),
               Vector((s*0.05, yb, vz(yb, 0.05)+0.045)), Vector((s*0.16, yb-0.06, vz(yb-0.06, 0.16)+0.045)), Vector((s*0.16, ya, vz(ya, 0.16)+0.045))],
          (s*0.003, 0, 0), mi=1)
prism(bm, [Vector((-0.16, ya, vz(ya, 0.16))), Vector((0.16, ya, vz(ya, 0.16))), Vector((0.16, ya, vz(ya, 0.16)+0.045)), Vector((-0.16, ya, vz(ya, 0.16)+0.045))], (0, -0.003, 0), mi=1)
mk("Bandeja_Carga_V", bm, cC, ["Bandeja_Blanca", "Naranja_Exergy"])
bm = bmesh.new()   # viga naranja bajo la canaleta + dos patas
ya, yb = Y_FRONT, -0.11
p = [Vector((-0.02, ya, zrail(ya)-0.025)), Vector((-0.02, yb, zrail(yb)-0.025)), Vector((-0.02, yb, zrail(yb)-0.065)), Vector((-0.02, ya, zrail(ya)-0.065))]
prism(bm, p, (0.04, 0, 0))
for y in (-0.53, -0.36):
    box(bm, (0, y, (zrail(y)-0.065+0.05)/2), (0.03, 0.03, zrail(y)-0.065-0.05))
for x in (-0.14, 0.14):
    box(bm, (x, -0.50, (vz(-0.5, 0.14)-0.004+0.05)/2), (0.02, 0.02, vz(-0.5, 0.14)-0.004-0.05))
mk("Viga_Canaleta", bm, cC, ["Naranja_Exergy"])
bm = bmesh.new()
for x, y in ((0, -0.53), (0, -0.36), (-0.14, -0.50), (0.14, -0.50)):
    cylZ(bm, 0.022, 0.008, 0.05, 32, (x, y), mi=0); cylZ(bm, 0.024, 0.0, 0.008, 32, (x, y), mi=1)
mk("Patas_Niveladoras", bm, cC, ["Acero_Inox", "Caucho_Negro"])

# ---------- escape: dos pasadores + leva (1 motor) -> sale UN huevo por ciclo ----------
def pin(name, y):
    bm = bmesh.new()
    cyl(bm, (0, 0, -0.06), (0, 0, 0), 0.003, 12)
    cyl(bm, (0, 0, -0.003), (0, 0, 0.001), 0.0045, 12, mi=1)
    return mk(name, bm, cC, ["Acero_Inox", "Caucho_Negro"], (0, y, 0))
PIN_UP = zrail(PIN_F) + 0.014
pF = pin("Pasador_Delantero", PIN_F); pR = pin("Pasador_Trasero", PIN_R)
pF.location.z = PIN_UP; pR.location.z = PIN_UP - 0.03
ym = (PIN_F+PIN_R)/2; zc_ = zrail(ym) - 0.075
bm = bmesh.new()
box(bm, (0.05, ym, zc_), (0.04, 0.05, 0.04))
cyl(bm, (0.03, ym, zc_), (0.0, ym, zc_), 0.004, 12)
box(bm, (-0.012, ym, zc_+0.03), (0.004, 0.07, 0.09), mi=1)
for y in (PIN_F, PIN_R): box(bm, (0, y, zrail(y)-0.03), (0.012, 0.012, 0.012), mi=1)
mk("Escape_Motor", bm, cC, ["Motor_Negro", "Acero_Inox"])
bm = bmesh.new()
pts = [Vector((0, 0.016*math.cos(a)*(1.3 if math.cos(a) > 0.7 else 1.0), 0.016*math.sin(a))) for a in [2*math.pi*k/24 for k in range(24)]]
prism(bm, pts, (0.008, 0, 0))
leva = mk("Leva_Escape", bm, cC, ["Naranja_Exergy"], (-0.004, ym, zc_))

# ---------- limpieza: cama de 2 cepillos + cepillo superior (todos empujan hacia el centro) ----------
bed = []
for k, y in enumerate((-0.225, -0.16)):
    o = brush(f"Cepillo_Cama_{k+1}", cL, 0.008, 0.025, 0.09, ntuft=16, axle=0.07)
    o.location = (0, y, zrail(y) + 0.004 - 0.025); o.rotation_euler = (0, 0, math.pi/2); bed.append(o)
RB = 0.04
topb = brush("Cepillo_Superior", cL, 0.016, RB, 0.10, ntuft=22, axle=0.07)
topb.location = (0, YBT, ezc(YBT) + ER + RB - 0.004); topb.rotation_euler = (0, 0, math.pi/2)
zt0 = topb.location.z
bm = bmesh.new()
ri, ro, xh, n = 0.05, 0.053, 0.068, 20
ring = [(math.cos(math.radians(-20+220*i/n)), math.sin(math.radians(-20+220*i/n))) for i in range(n+1)]
def V(r, c, x): return bm.verts.new((x, YBT - r*c[0], zt0 + r*c[1]))
oi = [V(ro, c, -xh) for c in ring]; oo = [V(ro, c, xh) for c in ring]
ii = [V(ri, c, -xh) for c in ring]; io = [V(ri, c, xh) for c in ring]
for i in range(n):
    bm.faces.new((oi[i], oi[i+1], oo[i+1], oo[i])); bm.faces.new((ii[i+1], ii[i], io[i], io[i+1]))
    bm.faces.new((oi[i+1], oi[i], ii[i], ii[i+1])); bm.faces.new((oo[i], oo[i+1], io[i+1], io[i]))
bm.faces.new((oi[0], oo[0], io[0], ii[0])); bm.faces.new((oi[-1], ii[-1], io[-1], oo[-1]))
for s in (-1, 1):
    x = s*(xh+0.003)
    prism(bm, [Vector((x, YB0-0.01, zrail(YB0)-0.05)), Vector((x, YB1+0.01, zrail(YB1)-0.05)),
               Vector((x, YB1+0.01, zt0+0.02)), Vector((x, YB0-0.01, zt0+0.02))], (s*0.004, 0, 0))
    box(bm, (x+s*0.002, (YB0+YB1)/2, (FOOT+zrail(YB1)-0.05)/2), (0.004, 0.02, zrail(YB1)-0.05-FOOT))
mk("Limpieza_Carcasa", bm, cL, ["Acero_Inox"])
bm = bmesh.new()
box(bm, (0, (YB0+YB1)/2, zrail(YBT)-0.065), (0.15, YB1-YB0+0.03, 0.004), mi=0)                     # bandeja de polvo
box(bm, (-0.09, (YB0+YB1)/2, (zrail(YBT)-0.05+zt0+0.02)/2), (0.012, YB1-YB0+0.04, zt0+0.07-zrail(YBT)), mi=1)  # cubre-correa
cyl(bm, (-0.096, YBT, zt0-0.07), (-0.17, YBT, zt0-0.07), 0.026, 32, mi=2)                            # motor de cepillos
mk("Limpieza_Motor_Correa", bm, cL, ["Bandeja_Blanca", "Naranja_Exergy", "Motor_Negro"])

# ---------- inspeccion: camara oscura, cuna basculante sobre celda de carga, LED inferior, camara ----------
ROD_DY, ROD_R = 0.012, 0.004
rod_z = Z_CR - math.sqrt((ER+ROD_R)**2 - ROD_DY**2)
bm = bmesh.new()   # cuna (origen en la varilla delantera = pivote hacia el centro)
for dy in (0.0, -2*ROD_DY):
    cyl(bm, (-0.026, dy, 0), (0.026, dy, 0), ROD_R, 16, mi=1)
for s in (-1, 1): box(bm, (s*0.028, -ROD_DY, -0.004), (0.004, 0.034, 0.014), mi=0)
box(bm, (0.033, -ROD_DY, -0.004), (0.006, 0.01, 0.006), mi=0)
cuna = mk("Cuna_Basculante", bm, cI, ["Acero_Inox", "Caucho_Negro"], (0, Y_CR+ROD_DY, rod_z))
HX, HY0, HY1, HZ0, HZ1 = 0.06, -0.105, 0.0, 0.168, 0.29
bm = bmesh.new()
box(bm, (0.04, Y_CR, rod_z-0.002), (0.0127, 0.08, 0.0127))            # celda de carga tipo barra
box(bm, (0.04, Y_CR-0.045, (HZ0+rod_z)/2), (0.0127, 0.012, rod_z-HZ0))
mk("Celda_Carga_Pesaje", bm, cI, ["Celda_Carga"])
bm = bmesh.new()
box(bm, (-0.045, Y_CR+ROD_DY, rod_z), (0.02, 0.02, 0.04))
mk("Servo_Cuna", bm, cI, ["Motor_Negro"])
bm = bmesh.new()
cylZ(bm, 0.011, HZ0-0.003, HZ0+0.003, 32, (0, Y_CR))
mk("LED_Retroiluminacion", bm, cI, ["LED_Retroiluminacion"])
bm = bmesh.new()   # camara oscura: piso con hueco del LED, pared de entrada con ranura, salida hacia el centro
box(bm, (0, (HY0-0.02)/2, HZ0-0.0015), (2*HX, -0.02-HY0, 0.003))
box(bm, (0, HY1, (HZ1+0.228)/2), (2*HX, 0.003, HZ1-0.228))
box(bm, (0, (HY0+HY1)/2, HZ1), (2*HX, HY1-HY0, 0.003))
box(bm, (-HX, (HY0+HY1)/2, (HZ0+HZ1)/2), (0.003, HY1-HY0, HZ1-HZ0))
zr_ = zrail(HY0)
box(bm, (0, HY0, (zr_+0.065+HZ1)/2), (2*HX, 0.003, HZ1-zr_-0.065))
for s in (-1, 1): box(bm, (s*(HX+0.04)/2, HY0, (zr_+0.065+zr_-0.012)/2), (HX-0.04, 0.003, 0.077))
box(bm, (0.0, HY0-0.06, zr_-0.03), (0.02, 0.12, 0.004))                # soporte a la viga
mk("Camara_Oscura", bm, cI, ["Negro_Mate"])
bm = bmesh.new()
box(bm, (HX, (HY0+HY1)/2, (HZ0+HZ1)/2), (0.003, HY1-HY0, HZ1-HZ0))
tapa = mk("Camara_Oscura_Tapa_Lateral", bm, cI, ["Negro_Mate"]); tapa.hide_viewport = True; tapa.hide_render = True
bm = bmesh.new()   # cortinas de caucho en entrada y salida
for y, z0 in ((HY0-0.003, zr_+0.012), (HY1+0.003, 0.2)):
    for k in range(5):
        box(bm, (-0.032+0.016*k, y, z0+0.024), (0.015, 0.0015, 0.048))
mk("Cortinas_Caucho", bm, cI, ["Caucho_Negro"])
bm = bmesh.new()
cylZ(bm, 0.016, HZ1+0.002, HZ1+0.035, 32, (0, Y_CR), mi=0)
cylZ(bm, 0.009, HZ1-0.012, HZ1+0.002, 32, (0, Y_CR), mi=1)
box(bm, (0, Y_CR, HZ1+0.045), (0.04, 0.04, 0.02), mi=0)
mk("Camara_Vision", bm, cI, ["Negro_Mate", "Lente_Vidrio"])
for x in (-HX+0.01, HX-0.01):   # postes de la camara oscura a la placa base
    bm = bmesh.new(); box(bm, (x, HY0-0.012, (ZP+HZ0)/2), (0.012, 0.012, HZ0-ZP)); mk("Poste_Camara", bm, cI, ["Acero_Inox"])   # fuera del alcance del canal (r>0.12)

# ---------- canal giratorio (reemplaza empujador + paleta): 1 motor paso a paso ----------
bm = bmesh.new()
box(bm, (0, 0, ZP+0.004+0.021), (0.042, 0.042, 0.042), mi=1)               # motor paso a paso
mk("Motor_Paso_a_Paso", bm, cA, ["Interruptor_Rojo", "Motor_Negro"])
bm = bmesh.new()
cylZ(bm, 0.008, ZP+0.046, zsp(0)-ER-0.002, 24, mi=1)                        # eje hueco
fl = lambda x: zsp(x) - ER
prism(bm, [Vector((-0.03, -0.031, fl(-0.03))), Vector((ROUT, -0.031, fl(ROUT))),
           Vector((ROUT, 0.031, fl(ROUT))), Vector((-0.03, 0.031, fl(-0.03)))], (0, 0, -0.003), mi=0)
for s in (-1, 1):
    prism(bm, [Vector((0.02, s*0.031, fl(0.02))), Vector((ROUT, s*0.031, fl(ROUT))),
               Vector((ROUT, s*0.031, fl(ROUT)+0.016)), Vector((0.02, s*0.031, fl(0.02)+0.016))], (0, s*0.003, 0), mi=0)
prism(bm, [Vector((-0.03, -0.031, fl(-0.03))), Vector((-0.03, 0.031, fl(-0.03))),
           Vector((-0.03, 0.031, fl(-0.03)+0.012)), Vector((-0.03, -0.031, fl(-0.03)+0.012))], (-0.003, 0, 0), mi=0)
canal = mk("Canal_Giratorio", bm, cA, ["Bandeja_Blanca", "Acero_Inox"])

# ---------- rampa y caja de rechazo (fecundados / sucios / fisurados) ----------
d_ = pol(1, REJ, 0); t_ = pol(1, REJ+90, 0)
R_A, R_B, Z_A, Z_B = 0.108, 0.30, fl(ROUT)-0.004, 0.06
def rp(r, w, dz=0.0): return d_*r + t_*w + Vector((0, 0, Z_A + (Z_B-Z_A)*(r-R_A)/(R_B-R_A) + dz))
bm = bmesh.new()
prism(bm, [rp(R_A, -0.035), rp(R_B, -0.035), rp(R_B, 0.035), rp(R_A, 0.035)], (0, 0, -0.003))
for w in (-0.036, 0.036):
    prism(bm, [rp(R_A, w), rp(R_B, w), rp(R_B, w, 0.025), rp(R_A, w, 0.025)], t_*0.003*(1 if w > 0 else -1))
for r in (0.17, 0.27):
    p = rp(r, 0); box(bm, (p.x, p.y, (FOOT+p.z-0.003)/2), (0.012, 0.012, p.z-0.003-FOOT))
mk("Rampa_Rechazo", bm, cA, ["Acero_Inox"])
RB0, RB1 = 0.30, 0.42
bm = bmesh.new()
def bp(r, w, z): return d_*r + t_*w + Vector((0, 0, z))
prism(bm, [bp(RB0, -0.07, FOOT), bp(RB1, -0.07, FOOT), bp(RB1, 0.07, FOOT), bp(RB0, 0.07, FOOT)], (0, 0, 0.006), mi=1)
for r in (RB0, RB1):
    prism(bm, [bp(r, -0.07, FOOT), bp(r, 0.07, FOOT), bp(r, 0.07, 0.075 if r == RB1 else 0.045), bp(r, -0.07, 0.075 if r == RB1 else 0.045)], d_*0.003)
for w in (-0.07, 0.07):
    prism(bm, [bp(RB0, w, FOOT), bp(RB1, w, FOOT), bp(RB1, w, 0.075), bp(RB0, w, 0.045)], t_*0.003*(1 if w > 0 else -1))
mk("Caja_Rechazo", bm, cA, ["Naranja_Exergy", "Espuma_Gris"])

# labios blancos en la entrada de cada bandeja
bm = bmesh.new()
for i in range(5):
    a0, a1 = ANG[i], ANG[i+1]
    pts = []
    for k in range(9):
        aa = a1 - (a1-a0)*k/8; pts.append(pol(R0, aa, 0))
    for k in range(17):
        aa = a0 + (a1-a0)*k/16
        u_ = abs((aa-(a0+a1)/2)/((a1-a0)/2))
        pts.append(pol(0.16 + 0.07*u_**2, aa, 0))
    pts = [Vector((p.x, p.y, tray_z(p, i)+0.0004)) for p in pts]
    prism(bm, pts, (0, 0, 0.0015))
mk("Labios_Bandejas", bm, cB, ["Aletas_Blancas"])

# logo
def logo(name, text, loc, rot, size):
    cu_ = bpy.data.curves.new(name, 'FONT'); cu_.body = text; cu_.size = size; cu_.extrude = 0.0006
    cu_.align_x = 'CENTER'; cu_.align_y = 'CENTER'; cu_.materials.append(M["Aletas_Blancas"])
    o_ = bpy.data.objects.new(name, cu_); cE.objects.link(o_); o_.parent = root
    o_.location = loc; o_.rotation_euler = rot
mid = (pol(RV, 70, 0)+pol(RV, 110, 0))/2
logo("Logo_Faldon", "exergy", (mid.x, mid.y+0.0008, (FOOT+ZOUT)/2), (math.radians(90), 0, math.radians(180)), 0.035)

# ================= HUEVO (malla con origen en su centro) =================
Lh, Bh, w = EGG_L, EGG_B, 0.0035
def rr(x):
    v = (Lh*Lh-4*x*x)/(Lh*Lh+8*w*x+4*w*w); return (Bh/2)*math.sqrt(max(v, 0))
bm = bmesh.new(); rings, segs = 36, 36
bot = bm.verts.new((0, 0, -Lh/2)); rows = []
for i in range(1, rings):
    t = i/rings; x = -Lh/2+Lh*(1-math.cos(math.pi*t))/2; r_ = rr(x)
    rows.append([bm.verts.new((r_*math.cos(2*math.pi*j/segs), r_*math.sin(2*math.pi*j/segs), x)) for j in range(segs)])
top = bm.verts.new((0, 0, Lh/2))
for j in range(segs):
    k = (j+1) % segs
    bm.faces.new((bot, rows[0][k], rows[0][j]))
    for a_, b_ in zip(rows, rows[1:]): bm.faces.new((a_[j], a_[k], b_[k], b_[j]))
    bm.faces.new((rows[-1][j], rows[-1][k], top))
meH = bpy.data.meshes.new("Huevo"); bm.to_mesh(meH); bm.free()
for p in meH.polygons: p.use_smooth = True
meH.materials.append(M["Cascara_Huevo"])

# ================= ANIMACION (ciclo de 2 s = 1800 huevos/h) =================
#  f0+0..3  : la leva baja el pasador delantero (y sube el trasero): sale UN huevo
#  f0+3..25 : rueda por gravedad, pasa por los cepillos y cae en la cuna de la camara oscura
#  f0+26..36: pesaje + LED + foto; mientras tanto el canal giratorio ya apunta a su bandeja
#  f0+38..42: la cuna bascula hacia el centro y el huevo cae al canal
#  f0+42..48: baja rodando por el canal hasta la bandeja y sigue rodando hasta el tope
TC, NC, K = 48, 18, 5
F = lambda c: 1 + c*TC
SPQ = EGG_B + 0.001
YQ0 = PIN_F - 0.003 - ER
random.seed(11)
def classify(wg, fert):
    if fert: return -1
    for j, lim in enumerate((73, 67, 60, 53)):
        if wg >= lim: return j
    return 4
info = []
for c in range(NC):
    wg = round(random.gauss(63, 6.5), 1); fert = random.random() < 0.15
    info.append((wg, fert, classify(wg, fert)))
# categoria de peso -> bandeja (Jumbo en el centro, como suele usarse la mas visible)
CAT_TRAY = [2, 1, 3, 0, 4]
CATS = ["Jumbo", "AAA", "AA", "A", "B"]
SLOT_T = [0.0, 0.06, -0.06, 0.12, -0.12]
count = [0]*5; nrej = 0

def key_egg(o, f, loc, roll, yaw):
    o.location = loc; o.rotation_euler = (roll, math.pi/2, yaw)
    o.keyframe_insert("location", frame=f); o.keyframe_insert("rotation_euler", frame=f)
def key_vis(o, f, hidden):
    o.hide_viewport = hidden; o.hide_render = hidden
    o.keyframe_insert("hide_viewport", frame=f); o.keyframe_insert("hide_render", frame=f)
def chute(y): return Vector((0, y, ezc(y)))
def croll(y): return -y/ER          # rodando hacia +Y con el eje largo en X (yaw=0)

eggs = []
spout_angle = 90.0
key_rot(canal, 2, 1, math.radians(spout_angle))
for i in range(NC + K + 1):
    o = bpy.data.objects.new(f"Huevo_{i+1:02d}", meH); cH.objects.link(o); o.parent = root
    o.rotation_mode = 'YXZ'
    eggs.append(o)
    spawn_c = max(0, i-K)
    y0 = YQ0 - (i-spawn_c)*SPQ
    key_egg(o, F(spawn_c), chute(y0), croll(y0), 0.0)
    if i > K:
        key_vis(o, 0, True); key_vis(o, F(spawn_c)+14, False)
    for c in range(spawn_c, min(i, NC)):
        k = i - c
        ya_, yb_ = YQ0 - k*SPQ, YQ0 - (k-1)*SPQ
        key_egg(o, F(c)+14, chute(ya_), croll(ya_), 0.0)
        key_egg(o, F(c)+22, chute(yb_), croll(yb_), 0.0)
    if i >= NC: continue
    c = i; f0 = F(c); wg, fert, cat = info[c]
    key_egg(o, f0+3, chute(YQ0), croll(YQ0), 0.0)
    key_egg(o, f0+7, chute(YB0+0.01), croll(YB0+0.01), 0.0)
    key_egg(o, f0+19, chute(YB1-0.005), croll(YB1-0.005) - 12.0, 0.0)          # los cepillos lo hacen girar de mas
    key_egg(o, f0+23, chute(Y_END), croll(Y_END) - 12.0, 0.0)
    cr = Vector((0, Y_CR, Z_CR))
    key_egg(o, f0+25, cr, croll(Y_CR) - 12.0, 0.0)
    key_egg(o, f0+38, cr, croll(Y_CR) - 12.0, 0.0)
    # destino del canal
    if cat < 0:
        th_deg = REJ
    else:
        t = CAT_TRAY[cat]; th_deg = (ANG[t]+ANG[t+1])/2
    # el canal gira mientras se pesa (nunca cruza el frente: angulos entre -50 y 170)
    key_rot(canal, 2, f0+26, math.radians(spout_angle)); key_rot(canal, 2, f0+36, math.radians(th_deg))
    spout_angle = th_deg
    th = math.radians(th_deg)
    yaw_t = min((th + math.pi/2, th - math.pi/2), key=lambda y: abs(y))
    sgn = 1 if abs(((yaw_t - (th + math.pi/2)) + math.pi) % (2*math.pi) - math.pi) < 1e-6 else -1
    r_base = croll(Y_CR) - 12.0
    cen = Vector((0, 0, zsp(0)))
    key_egg(o, f0+42, cen, r_base - 2.0, yaw_t)
    dvec = Vector((math.cos(th), math.sin(th), 0))
    outp = dvec*ROUT; outp.z = zsp(ROUT)
    key_egg(o, f0+47, outp, r_base - 2.0 + sgn*ROUT/ER, yaw_t)
    if cat < 0:
        k_ = nrej; nrej += 1
        endp = d_*(RB1 - 0.03 - (k_ // 3)*0.045) + t_*(-0.045 + (k_ % 3)*0.045) + Vector((0, 0, FOOT+0.006+ER))
        mid_ = rp(R_B, 0, ER+0.001)
        key_egg(o, f0+56, mid_, r_base - 2.0 + sgn*(ROUT+0.19)/ER, yaw_t)
        key_egg(o, f0+62, endp, r_base - 2.0 + sgn*(ROUT+0.3)/ER, yaw_t)
    else:
        n_ = count[t]; count[t] += 1
        row, slot = divmod(n_, len(SLOT_T))
        dn = RV*math.cos(HALF) - TR - ER - 0.001 - row*(EGG_B+0.002)
        tdir = pol(1, th_deg+90, 0)
        end_xy = tray_dir(t)*dn + tdir*SLOT_T[slot]
        end = Vector((end_xy.x, end_xy.y, tray_z(end_xy, t)+ER+0.001))
        mv = end - outp; dist = mv.length
        phi = math.atan2(mv.y, mv.x)
        key_egg(o, f0+47+int(8+36*dist), end, r_base - 2.0 + sgn*(ROUT+dist)/ER, yaw_t + (((phi-th)+math.pi) % (2*math.pi) - math.pi))
    # escape
    key_loc(pF, 2, f0, PIN_UP); key_loc(pF, 2, f0+3, PIN_UP-0.03)
    key_loc(pF, 2, f0+8, PIN_UP-0.03); key_loc(pF, 2, f0+11, PIN_UP)
    key_loc(pR, 2, f0, PIN_UP-0.03); key_loc(pR, 2, f0+3, PIN_UP)
    key_loc(pR, 2, f0+11, PIN_UP); key_loc(pR, 2, f0+14, PIN_UP-0.03)
    # cuna: bascula hacia el centro y vuelve
    key_rot(cuna, 0, f0+38, 0.0); key_rot(cuna, 0, f0+41, math.radians(-30)); key_rot(cuna, 0, f0+46, 0.0)
    # LED de retroiluminacion (ovoscopia)
    sock = led.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    for f_, v_ in ((f0+27, 0.0), (f0+28, 40.0), (f0+35, 40.0), (f0+36, 0.0)):
        sock.default_value = v_; sock.keyframe_insert("default_value", frame=f_)

for o in eggs:
    for fc in fcurves_of(o):
        if fc.data_path.startswith("hide"):
            for kp in fc.keyframe_points: kp.interpolation = 'CONSTANT'
for o in (pF, pR, cuna):
    for fc in fcurves_of(o):
        for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
for o, axis, tps in [(leva, 0, 0.5)] + [(b, 1, 4.0) for b in bed] + [(topb, 1, -5.0)]:
    key_rot(o, axis, 1, 0.0); key_rot(o, axis, 25, 2*math.pi*tps); linear_forever(o)
sc.frame_start, sc.frame_end = 1, F(NC) + 60

# ================= CAMARA Y LUCES =================
cam = bpy.data.objects.new("Camara", bpy.data.cameras.new("Camara")); sc.collection.objects.link(cam)
cam.data.lens = 40
def aim(o, loc, tgt):
    o.location = loc; o.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
CAM_MAIN = ((1.05, -1.25, 0.85), (0.0, -0.05, 0.12))
aim(cam, *CAM_MAIN); sc.camera = cam
sun = bpy.data.objects.new("Sol", bpy.data.lights.new("Sol", 'SUN')); sc.collection.objects.link(sun)
sun.rotation_euler = Euler((math.radians(35), math.radians(10), math.radians(25))); sun.data.energy = 3
sc.render.engine = 'BLENDER_EEVEE' if any(e.identifier == 'BLENDER_EEVEE' for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items) else sc.render.engine

# ================= MEDIDAS =================
bpy.context.view_layer.update()
mn = Vector((9, 9, 9)); mx = Vector((-9, -9, -9))
for ob in main.all_objects:
    if ob.type != 'MESH' or ob.name.startswith("Huevo") or ob.hide_render: continue
    for c in ob.bound_box:
        wv = ob.matrix_world @ Vector(c)
        mn = Vector(map(min, mn, wv)); mx = Vector(map(max, mx, wv))

# ================= VISTAS PREVIAS (workbench) =================
eng = sc.render.engine
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'MATERIAL'
sc.display.shading.show_shadows = True; sc.display.shading.show_cavity = True
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
shots = {"general": (F(6)+30, CAM_MAIN[0], CAM_MAIN[1]),
         "centro": (F(6)+44, (0.32, -0.30, 0.42), (0.0, -0.03, 0.16)),
         "canaleta": (F(6)+12, (0.45, -0.55, 0.45), (0.0, -0.25, 0.22)),
         "final": (F(NC)+55, (0.0, -1.45, 1.25), (0.0, 0.0, 0.05))}
for name, (fr, loc, tgt) in shots.items():
    sc.frame_set(fr); aim(cam, loc, tgt)
    sc.render.filepath = f"{PREV}_{name}.png"
    bpy.ops.render.render(write_still=True)
aim(cam, *CAM_MAIN)
sc.render.engine = eng
sc.frame_set(1)
sc.render.filepath = "//render_"
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("RESULT " + json.dumps({"medidas_cm": [round((mx-mn)[i]*100, 1) for i in range(3)],
                              "min_cm": [round(v*100, 1) for v in mn], "max_cm": [round(v*100, 1) for v in mx],
                              "frames": [sc.frame_start, sc.frame_end],
                              "por_bandeja": {CATS[k]: count[CAT_TRAY[k]] for k in range(5)}, "rechazados": nrej,
                              "saved": OUT}))
