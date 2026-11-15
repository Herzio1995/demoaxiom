"""
Ovum1_9: corrige dos interferencias del bastidor.

1. Carcasa inferior: su base sube al plano superior del bastidor (z = cara superior de los largueros);
   la parte de arriba sigue bajo la placa del mecanismo. La rejilla se rehace para la nueva altura.
2. Bandejas inferiores vs largueros delanteros: las bandejas bajan (z 0.0516 en su extremo) por debajo de la
   cara superior de los largueros. No se mueven las bandejas (cambiaria el recorrido de los huevos): los
   largueros delanteros se acortan hasta donde la bandeja pasa >= 1 mm por encima; las patas delanteras se
   retroceden bajo el nuevo extremo y se quitan las 2 escuadras que quedarian colgando.

Se aplica a la copia unida visible (Bastidor_Largueros_2020.003) y a las piezas sueltas ocultas.
Uso:  blender --background Ovum1_9.blend --python corregir_interferencias_ovum1_9.py [-- save]
"""
import bpy, bmesh, json, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
O = bpy.data.objects; sc = bpy.context.scene; vl = bpy.context.view_layer
EPS = 1e-4; CLEAR = 0.001
report = {"avisos": []}
J = O["Bastidor_Largueros_2020.003"]

def world_bm(o):
    bm = bmesh.new(); bm.from_mesh(o.data); bm.transform(o.matrix_world); return bm
def put_back(o, bm):
    bm.transform(o.matrix_world.inverted()); bm.to_mesh(o.data); o.data.update(); bm.free()
def comps(bm):
    bm.verts.ensure_lookup_table(); seen = set(); out = []
    for v in bm.verts:
        if v.index in seen: continue
        st = [v]; c = []; seen.add(v.index)
        while st:
            a = st.pop(); c.append(a)
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in seen: seen.add(b.index); st.append(b)
        out.append(c)
    return out
def mats_of(c):
    return {f.material_index for v in c for f in v.link_faces}
def slot(o, prefix):
    for i, m in enumerate(o.data.materials):
        if m and m.name.startswith(prefix): return i
    return None

# ---- geometria de referencia de los largueros delanteros (en la copia unida)
bm = world_bm(J); ia, ic, ie = slot(J, "Aluminio_2020"), slot(J, "Caucho_Patas"), slot(J, "Acero_Escuadra")
front = []      # (xa, xb, y0, y1, z0, z1) tubos delanteros: 25 mm, |x| ~0.19..0.215
for c in comps(bm):
    xs = [v.co.x for v in c]; ys = [v.co.y for v in c]; zs = [v.co.z for v in c]
    if mats_of(c) == {ia} and abs(max(xs) - min(xs) - 0.025) < 2e-4 and min(abs(x) for x in xs) > 0.15 and max(ys) > 0.3:
        front.append((min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
bm.free()
if len(front) != 2: report["avisos"].append(f"largueros delanteros encontrados: {len(front)}")
Z_TOP = max(f[5] for f in front)
Y_END_OLD = max(f[3] for f in front)

# ---- 2a. nuevo extremo: donde la bandeja inferior queda >= CLEAR sobre la cara superior del tubo
dg = bpy.context.evaluated_depsgraph_get()
def tray_z(x, y):
    org = Vector((x, y, 0.5))
    for _ in range(12):
        ok, loc, n, i, ob, m = sc.ray_cast(dg, org, Vector((0, 0, -1)), distance=1.0)
        if not ok: return None
        if ob.name in ("Bandeja 1", "Bandeja 4"): return loc.z
        org = loc + Vector((0, 0, -0.0003))
    return None
y_end = Y_END_OLD
y = 0.30
while y <= Y_END_OLD + 1e-6:
    bad = False
    for xa, xb, *_ in front:
        for k in range(6):
            x = xa + (xb - xa) * k / 5
            z = tray_z(x, y)
            if z is not None and z < Z_TOP + CLEAR: bad = True
    if bad: y_end = round(y - 0.001, 4); break
    y += 0.001
DY = y_end - Y_END_OLD
report["larguero_delantero"] = {"extremo_antes": round(Y_END_OLD, 4), "extremo_nuevo": y_end, "acortado_mm": round(-DY * 1000, 1)}

def shorten(o):
    """mueve el extremo delantero de los tubos (anillo + tapon) DY en y; patas delanteras debajo; quita
    escuadras que quedan mas alla del nuevo extremo"""
    bm = world_bm(o)
    a_, c_, e_ = slot(o, "Aluminio_2020"), slot(o, "Caucho_Patas"), slot(o, "Acero_Escuadra")
    p_ = slot(o, "PETG_Negro")
    moved = 0; feet = 0; kill = []
    for c in comps(bm):
        ms = mats_of(c); xs = [v.co.x for v in c]; ys = [v.co.y for v in c]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        in_strip = any(xa - EPS <= cx <= xb + EPS for xa, xb, *_ in front)
        if ms <= {a_, p_} and in_strip and max(ys) > Y_END_OLD - 0.009 - EPS:
            for v in c:
                if v.co.y > Y_END_OLD - 0.0085: v.co.y += DY; moved += 1          # anillo extremo + tapon
        elif ms == {c_} and in_strip and max(ys) > y_end - 0.002:
            for v in c: v.co.y += (y_end - 0.016) - cy                           # pata bajo el extremo
            feet += 1
    if e_ is not None:      # escuadras (por cara: en la copia unida pueden estar fundidas con los travesanos)
        kill = [f for f in bm.faces if f.material_index == e_ and all(v.co.y >= y_end - 0.0075 and abs(v.co.x) > 0.15 for v in f.verts)]
        if kill:
            bmesh.ops.delete(bm, geom=kill, context='FACES')
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    put_back(o, bm)
    return {"vertices_movidos": moved, "patas": feet, "caras_escuadra_quitadas": len(kill)}

report["copia_unida"] = shorten(J)
for nm in ("Bastidor_Largueros_2020", "Patas_Caucho", "Escuadras_Bastidor"):
    if O.get(nm): report[nm] = shorten(O[nm])

# ---- 1. carcasa inferior sobre el bastidor
car = O["Carcasa_Inferior"]
bm = world_bm(car)
xs = [v.co.x for v in bm.verts]; ys = [v.co.y for v in bm.verts]
CX0, CX1, CY0, CYF = min(xs), max(xs), min(ys), max(ys)
z_top_c = max(v.co.z for v in bm.verts); T = 0.003
# escuadras del bastidor (caras de acero) sobre las que apoyaria una pared: se deja una muesca encima
bj = world_bm(J); esc = []
for f in bj.faces:
    if f.material_index == ie:
        fx = [v.co.x for v in f.verts]; fy = [v.co.y for v in f.verts]; fz = [v.co.z for v in f.verts]
        esc.append((min(fx), max(fx), min(fy), max(fy), max(fz)))
bj.free()
walls = [(CX0, CX1, CY0, CY0 + T, 'x'), (CX0, CX1, CYF - T, CYF, 'x'), (CX0, CX0 + T, CY0, CYF, 'y'), (CX1 - T, CX1, CY0, CYF, 'y')]
bm.clear(); notches = 0
for xa, xb, ya, yb, ax in walls:
    lo, hi = (xa, xb) if ax == 'x' else (ya, yb)
    cuts = []
    for ex0, ex1, ey0, ey1, ez in esc:
        if ex1 > xa + EPS and ex0 < xb - EPS and ey1 > ya + EPS and ey0 < yb - EPS:
            a0, a1 = (ex0, ex1) if ax == 'x' else (ey0, ey1)
            cuts.append((max(lo, a0 - 0.0005), min(hi, a1 + 0.0005), ez + 0.0003))
    cuts.sort(); segs = []; cur = lo
    for c0, c1, cz in cuts:
        if c0 > cur: segs.append((cur, c0, Z_TOP))
        segs.append((max(c0, cur), c1, cz)); cur = max(cur, c1); notches += 1
    if cur < hi: segs.append((cur, hi, Z_TOP))
    for s0, s1, zb in segs:
        if s1 - s0 < 1e-6: continue
        X0, X1, Y0, Y1 = (s0, s1, ya, yb) if ax == 'x' else (xa, xb, s0, s1)
        g = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, verts=g['verts'], vec=(X1 - X0, Y1 - Y0, z_top_c - zb))
        bmesh.ops.translate(bm, verts=g['verts'], vec=((X0 + X1) / 2, (Y0 + Y1) / 2, (zb + z_top_c) / 2))
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
put_back(car, bm)
report["carcasa_muescas"] = notches
rej = O.get("Carcasa_Inferior_Rejilla")
if rej:
    bm = world_bm(rej)
    xs = [v.co.x for v in bm.verts]; ys = [v.co.y for v in bm.verts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    bm.clear()
    k = 0
    while True:
        zz = Z_TOP + 0.010 + k * 0.009
        if zz + 0.004 > z_top_c - 0.006: break
        g = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, verts=g['verts'], vec=(x1 - x0, y1 - y0, 0.004))
        bmesh.ops.translate(bm, verts=g['verts'], vec=((x0 + x1) / 2, (y0 + y1) / 2, zz + 0.002))
        k += 1
    put_back(rej, bm)
    report["rejilla_listones"] = k
report["carcasa_z"] = [round(Z_TOP, 4), round(z_top_c, 4)]

# ---- revision
dg = bpy.context.evaluated_depsgraph_get()
def bvh(o, shrink=0.0):
    oe = o.evaluated_get(dg); me = oe.to_mesh(); b = bmesh.new(); b.from_mesh(me); oe.to_mesh_clear()
    b.transform(o.matrix_world); t = BVHTree.FromBMesh(b); b.free(); return t
def box_bvh(xa, xb, ya, yb, za, zb):
    b = bmesh.new(); g = bmesh.ops.create_cube(b, size=1.0)
    bmesh.ops.scale(b, verts=g['verts'], vec=(xb - xa, yb - ya, zb - za))
    bmesh.ops.translate(b, verts=g['verts'], vec=((xa + xb) / 2, (ya + yb) / 2, (za + zb) / 2))
    t = BVHTree.FromBMesh(b); b.free(); return t
S = 0.0003     # encoge 0.3 mm para no contar apoyos (contacto) como choque
chk = {}
for xa, xb, y0, y1, z0, z1 in front:
    t = box_bvh(xa + S, xb - S, y0 + S, y_end - S, z0 + S, z1 - S)
    chk["larguero x=%.3f" % ((xa + xb) / 2)] = [n for n in ("Bandeja 1", "Bandeja 4") if t.overlap(bvh(O[n]))]
bc = world_bm(car); bmesh.ops.translate(bc, verts=bc.verts, vec=(0, 0, S)); tcar = BVHTree.FromBMesh(bc); bc.free()
chk["carcasa_choca_con"] = [o.name for o in vl.objects if o.type == 'MESH' and o.visible_get() and o not in (car, rej)
                            and not o.name.startswith("Huevo") and tcar.overlap(bvh(o))]
report["revision"] = chk
if "save" in argv:
    bpy.ops.wm.save_mainfile(); report["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(report))
