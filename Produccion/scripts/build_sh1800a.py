"""Clasificadora Exergy SH1800A - modelo v2 (ajustado con fotogramas del video) + animacion del ciclo.
Uso: blender --background --factory-startup --python build_sh1800a_v2.py -- OUT.blend PREVIEW_PREFIX
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

main = bpy.data.collections.new("Clasificadora_SH1800A"); sc.collection.children.link(main)
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
    if i in (0, 5):   # paneles laterales: de punta a punta, hasta las patas
        pts = [pol(R0, a, FOOT), pol(RV, a, FOOT), pol(RV, a, ZOUT+HD-0.004), pol(R0, a, ZIN+HD-0.004)]
        r_cap = R0
    else:             # divisores interiores: nacen en r=0.15 con un remate curvo
        pts = [pol(RD0, a, zl(RD0)-T), pol(RV, a, ZOUT-T), pol(RV, a, ZOUT+HD-0.004)]
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

# ================= CANALETA DE ALIMENTACION =================
Y0, Y1 = -0.075, YFRONT
Z0, Z1 = ZC-ER, 0.14             # fondo de la canaleta; baja suavemente hacia el centro
W, HW = EGG_B+0.005, 0.04
L = math.hypot(Y1-Y0, Z1-Z0); tilt = math.atan2(Z1-Z0, -(Y1-Y0))
RT = Matrix.Rotation(-tilt, 3, 'X')
def place(bm_, verts): xform(bm_, verts, RT, Vector((0, Y0, Z0)))
bm = bmesh.new()
place(bm, box(bm, (0, -L/2, -0.0015), (W+0.004, L, 0.003)))
for s in (-1, 1):
    place(bm, box(bm, (s*(W/2+0.001), -L/2, HW/2-0.003), (0.002, L, HW)))
    place(bm, box(bm, (s*(W/2+0.008), -L/2, HW-0.004), (0.014, L, 0.002)))   # pestanas
mk("Canaleta", bm, cC, ["Acero_Inox"])
bm = bmesh.new()
place(bm, box(bm, (0, -L/2-0.005, -0.025), (0.035, L-0.02, 0.045)))
zt = Z1-0.05
box(bm, (0, Y1+0.035, zt-0.004), (0.06, 0.06, 0.008))                      # placa de la pata
box(bm, (0, Y1+0.035, (0.05+zt)/2), (0.03, 0.03, zt-0.05))
mk("Viga_Canaleta", bm, cC, ["Naranja_Exergy"])
bm = bmesh.new()
cylZ(bm, 0.024, 0.008, 0.05, 40, (0, Y1+0.035), mi=0)
cylZ(bm, 0.026, 0.0, 0.008, 40, (0, Y1+0.035), mi=1)
mk("Pata_Niveladora", bm, cC, ["Acero_Inox", "Caucho_Negro"])
def chute_pos(s):   # centro del huevo a una distancia s desde el extremo interior
    return Vector((0, Y0, Z0)) + RT @ Vector((0, -s, ER))

# ================= MECANISMO CENTRAL (segun el video) =================
# peine de aletas blancas largas y finas entre la copa y las bandejas
bm = bmesh.new()
NF = 31
for k in range(NF):
    ang = -10 + 200*k/(NF-1)
    tmp = bmesh.new()
    pts = [Vector((0.042, -0.0035, 0)), Vector((0.15, -0.0012, 0)), Vector((0.15, 0.0012, 0)), Vector((0.042, 0.0035, 0))]
    prism(tmp, pts, (0, 0, 0.0015))
    SLOPE = math.atan((ZIN-ZOUT)/(RV-R0))      # misma pendiente que la bandeja
    xform(tmp, tmp.verts, Matrix.Rotation(SLOPE, 3, 'Y'), Vector((0, 0, ZIN+0.0035+R0*math.tan(SLOPE))))
    xform(tmp, tmp.verts, Matrix.Rotation(math.radians(ang), 3, 'Z'))
    me = bpy.data.meshes.new("tmp"); tmp.to_mesh(me); tmp.free(); bm.from_mesh(me); bpy.data.meshes.remove(me)
mk("Aletas_Peine", bm, cA, ["Aletas_Blancas"])

# labios blancos en la entrada de cada bandeja (borde curvo, como en el video)
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

# motor paso a paso bajo el centro + dos soportes de acero en U (con pies atornillados)
bm = bmesh.new()
box(bm, (0, 0, ZP+0.004+0.021), (0.042, 0.042, 0.042))
box(bm, (0.0212, 0, ZP+0.004+0.021), (0.001, 0.03, 0.025), mi=1)
mk("Motor_Paso_a_Paso", bm, cA, ["Motor_Negro", "Interruptor_Rojo"])
bm = bmesh.new()
ZB = ZP+0.004; ZT = 0.1
for y in (-0.032, 0.032):
    for s in (-1, 1):
        box(bm, (s*0.03, y, (ZB+ZT)/2), (0.002, 0.022, ZT-ZB))        # patas
        box(bm, (s*0.04, y, ZB+0.001), (0.02, 0.022, 0.002))          # pies
    box(bm, (0, y, ZT), (0.062, 0.022, 0.002))                        # puente
# compuerta de salida de la canaleta: servo (lado +X) con soporte de acero
GY = Y0 + 0.004; GZ = ZC + ER + 0.006
box(bm, (0.064, GY+0.012, (ZB+GZ-0.02)/2), (0.024, 0.002, GZ-0.02-ZB))
box(bm, (0.064, GY+0.002, GZ-0.021), (0.024, 0.022, 0.002))
mk("Soportes_Acero", bm, cA, ["Acero_Inox"])
bm = bmesh.new()
box(bm, (0.064, GY, GZ), (0.024, 0.02, 0.04))
box(bm, (0.064, GY-0.0105, GZ), (0.016, 0.001, 0.02), mi=1)
mk("Servo_Compuerta", bm, cA, ["Motor_Negro", "Interruptor_Rojo"])
bm = bmesh.new()
v = cylZ(bm, 0.0055, 0, 0.01, 20); xform(bm, v, Matrix.Rotation(math.radians(90), 3, 'Y'), Vector((0.042, GY, GZ)))
mk("Acople_Laton", bm, cA, ["Laton"])
# eje + dos aletas blancas curvas (origen en el eje: gira en X para dejar pasar un huevo)
bm = bmesh.new()
v = cylZ(bm, 0.0018, -0.03, 0.042, 12, mi=1); xform(bm, v, Matrix.Rotation(math.radians(90), 3, 'Y'))
for xs in (-0.012, 0.012):
    pts = []
    for k in range(9):
        t_ = k/8; pts.append(Vector((xs-0.0008, -0.004 - 0.006*math.sin(math.pi*t_), -0.036*t_)))
    for k in range(7, 0, -1):
        t_ = k/8; pts.append(Vector((xs-0.0008, 0.004 + 0.002*math.sin(math.pi*t_) - 0.004*t_, -0.036*t_)))
    pts.append(Vector((xs-0.0008, 0.004, 0)))
    prism(bm, pts, (0.0016, 0, 0))
compuerta = mk("Compuerta_Aletas", bm, cA, ["Aletas_Blancas", "Acero_Inox"], (0, GY, GZ))

# brazos amarillos de pesaje (fijos, sobre la celda de carga) en estrella bajo el huevo
AY, BX = EGG_L/2, ER                       # semiejes del huevo (largo en Y, ancho en X/Z)
def egg_bottom(x, y):
    q = 1 - (x/BX)**2 - (y/AY)**2
    return ZC - BX*math.sqrt(max(q, 0.0))
arms = bpy.data.curves.new("Brazos_Pesaje", 'CURVE'); arms.dimensions = '3D'
arms.bevel_depth = 0.0024; arms.bevel_resolution = 3
for ang in (30, 90, 150, 210, 270, 330):
    d = pol(1, ang, 0)
    pts = [Vector((d.x*0.003, d.y*0.003, 0.109))]
    for k in range(1, 9):
        rho = 0.003 + 0.027*k/8
        x, y = d.x*rho, d.y*rho
        cap = 0.131 + 0.004*(k-6) if k > 6 else 1.0          # punta levantada
        pts.append(Vector((x, y, min(egg_bottom(x, y) - 0.0026, cap))))
    sp = arms.splines.new('POLY'); sp.points.add(len(pts)-1)
    for P, pt in zip(sp.points, pts): P.co = (pt.x, pt.y, pt.z, 1)
arms.materials.append(M["Laton"])
brz = bpy.data.objects.new("Brazos_Pesaje", arms); cA.objects.link(brz); brz.parent = root
bm = bmesh.new()
cylZ(bm, 0.003, ZT, 0.11, 12)                                        # vastago a la celda de carga
mk("Vastago_Pesaje", bm, cA, ["Laton"])

# empujador giratorio: tubo sobre el motor, brazo radial y paleta blanca abatible
bm = bmesh.new()
cylZ(bm, 0.0065, ZT+0.001, 0.104, 24)
box(bm, (0, 0.018, 0.102), (0.008, 0.036, 0.004))
box(bm, (0, 0.036, 0.1135), (0.006, 0.004, 0.027))
emp = mk("Empujador", bm, cA, ["Aletas_Blancas"])
bm = bmesh.new()
pts = [Vector((-0.014, 0, 0)), Vector((0.014, 0, 0)), Vector((0.014, 0, 0.026))]
pts += [Vector((0.014*math.cos(math.pi*k/8), 0, 0.026 + 0.009*math.sin(math.pi*k/8))) for k in range(1, 8)]
pts += [Vector((-0.014, 0, 0.026))]
prism(bm, pts, (0, 0.003, 0))
paleta = mk("Paleta_Empuje", bm, cA, ["Aletas_Blancas"], (0, 0.0345, 0.127))
paleta.parent = emp

# logo en el faldon trasero y en la placa base
def logo(name, text, loc, rot, size):
    cu_ = bpy.data.curves.new(name, 'FONT'); cu_.body = text; cu_.size = size; cu_.extrude = 0.0006
    cu_.align_x = 'CENTER'; cu_.align_y = 'CENTER'; cu_.materials.append(M["Aletas_Blancas"])
    o_ = bpy.data.objects.new(name, cu_); cE.objects.link(o_); o_.parent = root
    o_.location = loc; o_.rotation_euler = rot
mid = (pol(RV, 70, 0)+pol(RV, 110, 0))/2
logo("Logo_Faldon", "exergy", (mid.x, mid.y+0.0008, (FOOT+ZOUT)/2), (math.radians(90), 0, math.radians(180)), 0.035)
logo("Logo_Placa", "exergy", (0.0, -0.11, ZP+0.0045), (0, 0, 0), 0.025)

# ================= HUEVO (malla con origen en su centro) =================
Lh, Bh, w = EGG_L, EGG_B, 0.0035
def rr(x):
    v = (Lh*Lh-4*x*x)/(Lh*Lh+8*w*x+4*w*w); return (Bh/2)*math.sqrt(max(v, 0))
bm = bmesh.new(); rings, segs = 40, 40
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

# ================= ANIMACION =================
# Ciclo de 2 s por huevo (1800 huevos/h a 24 fps = 48 frames), segun el video:
#   0-14 : la compuerta (dos aletas blancas) se abre y deja pasar UN huevo a los brazos amarillos
#   12-20: la fila avanza y el siguiente huevo queda apoyado en la compuerta
#   10-18: pesaje
#   16-26: el empujador gira y coloca la paleta detras del huevo (lado opuesto a la bandeja)
#   26-31: la paleta se abate y lanza el huevo sobre el peine de aletas
#   31-..: el huevo rueda pendiente abajo hasta el tope (o hasta los que ya estan)
#   34-44: el empujador vuelve a su posicion (paleta en +Y, hace de tope al huevo que entra)
TC, NC, K = 48, 20, 5
SP = EGG_L + 0.002
S0 = (0.026 + 0.0015) / math.cos(tilt)      # primer huevo apoyado en la compuerta
F = lambda c: 1 + c*TC
random.seed(7)
weights = [0.14, 0.24, 0.3, 0.2, 0.12]
targets = random.choices(range(5), weights=weights, k=NC)
SLOT_T = [0.0, 0.06, -0.06, 0.12, -0.12]
count = [0]*5
def wrap(a): return (a + math.pi) % (2*math.pi) - math.pi

def key_egg(o, f, loc, roll, yaw):
    o.location = loc; o.rotation_euler = (roll, math.pi/2, yaw)
    o.keyframe_insert("location", frame=f); o.keyframe_insert("rotation_euler", frame=f)
def key_vis(o, f, hidden):
    o.hide_viewport = hidden; o.hide_render = hidden
    o.keyframe_insert("hide_viewport", frame=f); o.keyframe_insert("hide_render", frame=f)
def key_rot(o, axis, f, val):
    o.rotation_euler[axis] = val; o.keyframe_insert("rotation_euler", index=axis, frame=f)

GATE_OPEN = math.radians(100); KICK = math.radians(55)
key_rot(compuerta, 0, 1, 0); key_rot(emp, 2, 1, 0); key_rot(paleta, 0, 1, 0)
eggs = []
for i in range(NC + K + 1):
    o = bpy.data.objects.new(f"Huevo_{i+1:02d}", meH); cH.objects.link(o); o.parent = root
    o.rotation_mode = 'YXZ'      # R = Rz(yaw) @ Rx(roll) @ Ry(90): eje largo del huevo = direccion "yaw"
    eggs.append(o)
    spawn_c = max(0, i-K)
    key_egg(o, F(spawn_c), chute_pos(S0 + (i-spawn_c)*SP), 0, math.pi/2)
    if i > K:
        key_vis(o, 0, True); key_vis(o, F(spawn_c)+12, False)
    for c in range(spawn_c, min(i, NC)):
        k = i - c
        key_egg(o, F(c)+12, chute_pos(S0 + k*SP), 0, math.pi/2)
        key_egg(o, F(c)+20, chute_pos(S0 + (k-1)*SP), 0, math.pi/2)
    if i >= NC:
        continue
    # --- este huevo se clasifica en el ciclo c = i ---
    c = i; t = targets[c]; f0 = F(c)
    th = math.radians((ANG[t]+ANG[t+1])/2)
    cen = Vector((0, 0, ZC))
    key_egg(o, f0+2, chute_pos(S0), 0, math.pi/2)
    key_egg(o, f0+10, cen, 0, math.pi/2)
    key_egg(o, f0+26, cen, 0, math.pi/2)
    # al salir gira para quedar transversal a su direccion y rodar
    yaw_rel = min((th + math.pi/2, th - math.pi/2), key=lambda y: abs(y - math.pi/2))
    sgn = 1 if abs(wrap(yaw_rel - (th + math.pi/2))) < 1e-6 else -1
    rel_xy = Vector((math.cos(th), math.sin(th), 0))*0.115
    rel = Vector((rel_xy.x, rel_xy.y, tray_z(rel_xy, t)+ER+0.0055))   # sobre el peine de aletas
    key_egg(o, f0+31, rel, sgn*0.115/ER*0.5, yaw_rel)
    # posicion final: filas contra el tope, de centro hacia los lados
    n_ = count[t]; count[t] += 1
    row, slot = divmod(n_, len(SLOT_T))
    dn = RV*math.cos(HALF) - TR - ER - 0.001 - row*(EGG_B+0.002)
    tdir = pol(1, math.degrees(th)+90, 0)
    end_xy = tray_dir(t)*dn + tdir*SLOT_T[slot]
    end = Vector((end_xy.x, end_xy.y, tray_z(end_xy, t)+ER+0.001))
    mv = end - rel; dist = mv.length
    phi = math.atan2(mv.y, mv.x)
    yaw_end = yaw_rel + wrap(phi - th)
    fend = f0+31 + int(10 + 40*dist)         # ruedan mas los que van mas lejos
    key_egg(o, fend, end, sgn*(0.115/ER*0.5 + dist/ER), yaw_end)
    # compuerta: abre, deja pasar uno, cierra
    key_rot(compuerta, 0, f0, 0); key_rot(compuerta, 0, f0+4, GATE_OPEN)
    key_rot(compuerta, 0, f0+10, GATE_OPEN); key_rot(compuerta, 0, f0+14, 0)
    # empujador: la paleta (en +Y local) va al lado opuesto de la bandeja, se abate y vuelve
    phi_e = wrap(th + math.pi - math.pi/2)
    key_rot(emp, 2, f0+16, 0); key_rot(emp, 2, f0+26, phi_e); key_rot(emp, 2, f0+34, phi_e); key_rot(emp, 2, f0+44, 0)
    key_rot(paleta, 0, f0+26, 0); key_rot(paleta, 0, f0+29, KICK); key_rot(paleta, 0, f0+34, 0)

def fcurves_of(idb):
    ad = idb.animation_data; act = ad.action
    try:
        return [fc for ly in act.layers for st in ly.strips for fc in st.channelbag(ad.action_slot).fcurves]
    except AttributeError:
        return list(act.fcurves)
for o in eggs:
    for fc in fcurves_of(o):
        if fc.data_path.startswith("hide"):
            for kp in fc.keyframe_points: kp.interpolation = 'CONSTANT'
        elif fc.data_path == "rotation_euler" and fc.array_index == 0:
            for kp in fc.keyframe_points: kp.interpolation = 'BEZIER'
sc.frame_start, sc.frame_end = 1, F(NC) + 40

# ================= CAMARA Y LUCES =================
cam = bpy.data.objects.new("Camara", bpy.data.cameras.new("Camara")); sc.collection.objects.link(cam)
cam.data.lens = 40
def aim(o, loc, tgt):
    o.location = loc; o.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
aim(cam, (0.95, -1.05, 0.62), (0.0, 0.03, 0.1))
sc.camera = cam
sun = bpy.data.objects.new("Sol", bpy.data.lights.new("Sol", 'SUN')); sc.collection.objects.link(sun)
sun.rotation_euler = Euler((math.radians(35), math.radians(10), math.radians(25))); sun.data.energy = 3
sc.render.engine = 'BLENDER_EEVEE' if any(e.identifier == 'BLENDER_EEVEE' for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items) else sc.render.engine

# ================= MEDIDAS =================
bpy.context.view_layer.update()
mn = Vector((9, 9, 9)); mx = Vector((-9, -9, -9))
for ob in main.all_objects:
    if ob.type != 'MESH' or ob.name.startswith("Huevo"): continue
    for c in ob.bound_box:
        wv = ob.matrix_world @ Vector(c)
        mn = Vector(map(min, mn, wv)); mx = Vector(map(max, mx, wv))

# ================= VISTAS PREVIAS (workbench) =================
eng = sc.render.engine
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'MATERIAL'
sc.display.shading.show_shadows = True; sc.display.shading.show_cavity = True
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
shots = {"a": (F(3)+28, (0.95, -1.05, 0.62), (0.0, 0.03, 0.1)),     # paleta empujando
         "b": (F(NC)+30, (0.0, -1.2, 0.95), (0.0, 0.08, 0.05)),     # final: huevos clasificados
         "c": (F(5)+29, (0.25, -0.45, 0.32), (0.0, -0.05, 0.12))}   # detalle mecanismo
for name, (fr, loc, tgt) in shots.items():
    sc.frame_set(fr); aim(cam, loc, tgt)
    sc.render.filepath = f"{PREV}_{name}.png"
    bpy.ops.render.render(write_still=True)
aim(cam, (0.95, -1.05, 0.62), (0.0, 0.03, 0.1))
sc.render.engine = eng
sc.frame_set(1)
sc.render.filepath = "//render_"
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("RESULT " + json.dumps({"medidas_cm": [round((mx-mn)[i]*100, 1) for i in range(3)],
                              "min_cm": [round(v*100, 1) for v in mn], "max_cm": [round(v*100, 1) for v in mx],
                              "frames": [sc.frame_start, sc.frame_end], "por_bandeja": count,
                              "saved": OUT}))
