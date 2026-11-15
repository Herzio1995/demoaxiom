"""
Ovum1_9: todos los fierros del bastidor (travesanos, diagonales de la transicion, postes y travesano bajo las
bandejas superiores) pasan de 20x20 a tubo cuadrado de 25x25 mm. Los largueros ya estaban en 25 mm.

Criterios (para no mover lo que ya apoya en el bastidor):
  - Travesanos y diagonales a nivel del bastidor: a ras arriba (z 0.0539) con los largueros; crecen 5 mm hacia
    abajo y 2.5 mm a cada lado. Sus extremos siguen contra la cara interior de los largueros.
  - El travesano que remata los largueros traseros cubre todo su ancho nuevo; los largueros traseros se acortan
    hasta su cara trasera.
  - Diagonales: sus dos caras largas se desplazan 2.5 mm hacia afuera; se recortan contra ese travesano y el
    inicio del larguero delantero.
  - Postes: crecen alrededor de su eje (los que van pegados a un larguero crecen hacia adentro); base y altura
    iguales.
  - Travesano bajo las bandejas superiores: queda a 0.5 mm bajo la bandeja superior; el poste central y las
    cartelas se ajustan debajo. Paso libre para los huevos de la bandeja inferior: se informa.
Uso:  blender --background Ovum1_9.blend --python bastidor_25mm_ovum1_9.py [-- save]
"""
import bpy, bmesh, json, sys, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
O = bpy.data.objects; sc = bpy.context.scene; vl = bpy.context.view_layer
S = 0.025; H = S / 2; G = 0.0025; EPS = 2e-4
Z_TOP = 0.0539; Z_BOT = Z_TOP - S
report = {"avisos": []}

def slot(o, prefix, fallback=None):
    for i, m in enumerate(o.data.materials):
        if m and m.name.startswith(prefix): return i
    if fallback:
        m = bpy.data.materials.get(fallback)
        if m: o.data.materials.append(m); return len(o.data.materials) - 1
    return None
def wbm(o):
    bm = bmesh.new(); bm.from_mesh(o.data); bm.transform(o.matrix_world); return bm
def put(o, bm):
    bm.transform(o.matrix_world.inverted()); bm.to_mesh(o.data); o.data.update(); bm.free()
def fb(f):
    return [[min(v.co[i] for v in f.verts), max(v.co[i] for v in f.verts)] for i in range(3)]

# ------------------------------------------------ largueros (tubos de 25 mm ya hechos), referencia global
J = O["Bastidor_Largueros_2020.003"]
def tubes_of(o):
    """tubos huecos 25 mm: componentes de aluminio de 16 vertices con lado 0.025"""
    ia = slot(o, "Aluminio_2020"); bm = wbm(o); bm.verts.ensure_lookup_table(); seen = set(); out = []
    for v in bm.verts:
        if v.index in seen: continue
        st = [v]; c = []; seen.add(v.index)
        while st:
            a = st.pop(); c.append(a)
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in seen: seen.add(b.index); st.append(b)
        ms = {f.material_index for q in c for f in q.link_faces}
        xs = [q.co.x for q in c]; ys = [q.co.y for q in c]; zs = [q.co.z for q in c]
        if ms == {ia} and len(c) == 16 and abs(max(xs) - min(xs) - S) < EPS and abs(max(zs) - min(zs) - S) < EPS:
            out.append([min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)])
    bm.free(); return out
TUBES = tubes_of(J)
if len(TUBES) != 4: report["avisos"].append(f"largueros encontrados en la copia unida: {len(TUBES)}")
REAR = [t for t in TUBES if t[3] < -0.05]; FRONT = [t for t in TUBES if t[3] > 0.2]
INNER_PLANES = []          # (x, y0, y1) caras interiores de los largueros
for t in TUBES:
    xi = t[0] if t[0] > 0 else t[1]
    INNER_PLANES.append((xi, t[2], t[3]))
REAR_OUT = max(abs(t[0]) if t[0] < 0 else t[1] for t in REAR) if REAR else 0.0983
REAR_END = max(t[3] for t in REAR) if REAR else -0.1082

def snap_x(x, y0, y1):
    """si un extremo esta a <4 mm de la cara interior de un larguero, lo pega a ella"""
    best = None
    for xi, a, b in INNER_PLANES:
        if b > y0 - 0.003 and a < y1 + 0.003 and abs(x - xi) < 0.004 and (best is None or abs(x - xi) < abs(x - best)):
            best = xi
    return best if best is not None else x

# ------------------------------------------------ geometria nueva
def add_box(bm, x0, x1, y0, y1, z0, z1, mi):
    g = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=g['verts'], vec=(x1 - x0, y1 - y0, z1 - z0))
    bmesh.ops.translate(bm, verts=g['verts'], vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    for f in {f for v in g['verts'] for f in v.link_faces}: f.material_index = mi
def add_prism(bm, poly, z0, z1, mi):
    a = [bm.verts.new((x, y, z0)) for x, y in poly]; b = [bm.verts.new((x, y, z1)) for x, y in poly]
    fs = [bm.faces.new(list(reversed(a))), bm.faces.new(b)]
    n = len(poly)
    for i in range(n): fs.append(bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i])))
    for f in fs: f.material_index = mi
def clip(poly, nx, ny, c):
    """conserva la parte con nx*x + ny*y <= c"""
    out = []
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        dp, dq = nx * p[0] + ny * p[1] - c, nx * q[0] + ny * q[1] - c
        if dp <= 0: out.append(p)
        if (dp < 0) != (dq < 0) and dp != dq:
            t = dp / (dp - dq); out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out

dg = bpy.context.evaluated_depsgraph_get()
def tray_min_z(x0, x1, y0, y1, names):
    zmin = None
    for i in range(9):
        for j in range(5):
            org = Vector((x0 + (x1 - x0) * i / 8, y0 + (y1 - y0) * j / 4, 0.5))
            for _ in range(12):
                ok, loc, n, k, ob, m = sc.ray_cast(dg, org, Vector((0, 0, -1)), distance=1.0)
                if not ok: break
                if ob.name in names:
                    zmin = loc.z if zmin is None else min(zmin, loc.z); break
                org = loc + Vector((0, 0, -0.0003))
    return zmin

def convert(o, is_joined):
    ia = slot(o, "Aluminio_2020"); ip = slot(o, "PETG_Negro")
    if ia is None: return None
    bm = wbm(o); bm.faces.ensure_lookup_table()
    in_tube = lambda f: any(t[0] - EPS <= fb(f)[0][0] and fb(f)[0][1] <= t[1] + EPS and t[2] - EPS <= fb(f)[1][0]
                            and fb(f)[1][1] <= t[3] + EPS and fb(f)[2][0] >= t[4] - EPS and fb(f)[2][1] <= t[5] + EPS for t in TUBES)
    alu = [f for f in bm.faces if f.material_index == ia and not in_tube(f)]
    # cartabones aplanados de los postes (prismas de 6 vertices): se conservan y se corren 2.5 mm hacia afuera
    keep = set(); vseen = set()
    for f in alu:
        comp = set(); st = [f]; comp.add(f)
        while st:
            a = st.pop()
            for e in a.edges:
                for g in e.link_faces:
                    if g.material_index == ia and g not in comp and not in_tube(g): comp.add(g); st.append(g)
        vs = {v for g in comp for v in g.verts}
        if len(vs) == 6 and id(f) not in vseen:
            for g in comp: keep.add(g)
            cx = sum(v.co.x for v in vs) / 6
            if not any(v.index in vseen for v in vs):
                for v in vs: v.co.x += G * (1 if cx > 0 else -1); vseen.add(v.index)
    alu = [f for f in alu if f not in keep]

    # ---- 1. travesanos a nivel del bastidor: caras superiores rectangulares de 20 mm de ancho en y
    trav = {}
    for f in alu:
        b = fb(f)
        if f.normal.z > 0.9 and abs(b[2][0] - Z_TOP) < EPS and len(f.verts) == 4 and abs(b[1][1] - b[1][0] - 0.020) < 5e-4 \
           and b[0][1] - b[0][0] > 0.03 and all(abs(v.co.x - b[0][0]) < EPS or abs(v.co.x - b[0][1]) < EPS for v in f.verts):
            k = (round(b[1][0], 3), round(b[1][1], 3))
            x0, x1 = trav.get(k, (9, -9)); trav[k] = (min(x0, b[0][0]), max(x1, b[0][1]))
    # ---- 2. diagonales: caras verticales no alineadas a los ejes (la mas larga de cada orientacion por lado)
    diag = {}
    for f in alu:
        n = f.normal
        if abs(n.z) < 0.1 and abs(n.x) > 0.3 and abs(n.y) > 0.3:
            b = fb(f); side = 1 if (b[0][0] + b[0][1]) > 0 else -1
            ln = math.hypot(b[0][1] - b[0][0], b[1][1] - b[1][0])
            key = (side, 'out' if (n.y < 0) else 'in')
            if key not in diag or ln > diag[key][0]:
                p = [v.co.copy() for v in f.verts]
                diag[key] = (ln, (n.x, n.y), p[0])
    # ---- 3. postes y travesano superior: grupos de caras sobre el bastidor
    up = [f for f in alu if fb(f)[2][0] >= Z_TOP - EPS and fb(f)[2][1] > Z_TOP + 0.005]
    wide = lambda f: fb(f)[0][1] - fb(f)[0][0] > 0.05
    def group(faces):
        gs = []
        for f in faces:
            b = fb(f); hit = None
            for g in gs:
                if b[0][0] < g[1] + EPS and b[0][1] > g[0] - EPS and b[1][0] < g[3] + EPS and b[1][1] > g[2] - EPS and b[2][0] < g[5] + EPS and b[2][1] > g[4] - EPS:
                    hit = g; break
            if hit:
                hit[0] = min(hit[0], b[0][0]); hit[1] = max(hit[1], b[0][1]); hit[2] = min(hit[2], b[1][0])
                hit[3] = max(hit[3], b[1][1]); hit[4] = min(hit[4], b[2][0]); hit[5] = max(hit[5], b[2][1])
            else:
                gs.append([b[0][0], b[0][1], b[1][0], b[1][1], b[2][0], b[2][1]])
        return gs
    groups = group([f for f in up if not wide(f)])
    tsup_g = group([f for f in alu if wide(f) and fb(f)[2][0] > 0.08])
    posts = [g for g in groups if g[5] - g[4] > 0.03 and g[1] - g[0] < 0.03]
    tsup = [g for g in tsup_g if g[1] - g[0] > 0.1]

    # ---- borrar el aluminio viejo (salvo largueros y cartabones)
    bmesh.ops.delete(bm, geom=alu, context='FACES')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')

    info = {"travesanos": [], "diagonales": 0, "postes": [], "travesano_superior": None}
    global T0_REAR, Z_TS0, TSUP_Y
    for (y0, y1) in trav:
        if y0 - 0.003 <= REAR_END <= y1 + 0.003: T0_REAR = ((y0 + y1) / 2 - H, (y0 + y1) / 2 + H)
    if T0_REAR:          # largueros traseros hasta la cara trasera del travesano de remate (solo el tubo)
        dy = T0_REAR[0] - REAR_END
        tv = {v for f in bm.faces if f.material_index in (ia, ip) for v in f.verts
              if any(t[0] - EPS <= v.co.x <= t[1] + EPS and t[4] - EPS <= v.co.z <= t[5] + EPS for t in REAR)
              and REAR_END - 0.0086 <= v.co.y <= REAR_END + EPS}
        tv = {v for v in tv if all((f.material_index == ia and in_tube(f)) or f.material_index == ip for f in v.link_faces)}
        for v in tv: v.co.y += dy
        if tv: info["largueros_traseros_acortados_mm"] = round(-dy * 1000, 1); info["vertices_extremo"] = len(tv)
    # travesanos nuevos
    t0_rear = None
    for (y0, y1), (x0, x1) in sorted(trav.items()):
        yc = (y0 + y1) / 2
        if y0 - 0.003 <= REAR_END <= y1 + 0.003:            # remate de los largueros traseros
            x0, x1 = -REAR_OUT, REAR_OUT; t0_rear = (yc - H, yc + H); T0_REAR = t0_rear
        else:
            x0, x1 = snap_x(x0, yc - H, yc + H), snap_x(x1, yc - H, yc + H)
        add_box(bm, x0, x1, yc - H, yc + H, Z_BOT, Z_TOP, ia)
        info["travesanos"].append([round(yc, 4), round(x0, 4), round(x1, 4)])
    # diagonales
    for side in (-1, 1):
        if (side, 'out') not in diag or (side, 'in') not in diag: continue
        _, (nox, noy), po = diag[(side, 'out')]; _, (nix, niy), pi = diag[(side, 'in')]
        co = nox * po.x + noy * po.y + G; ci = nix * pi.x + niy * pi.y + G
        big = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        poly = clip(big, nox, noy, co); poly = clip(poly, nix, niy, ci)
        y_front = min(t[2] for t in FRONT if (t[0] + t[1]) * side > 0) if FRONT else -0.0141
        x_out = max(abs(t[0]), abs(t[1])) if FRONT else 0.215
        y_back = t0_rear[0] if t0_rear else -0.1105
        poly = clip(poly, 0, 1, y_front); poly = clip(poly, 0, -1, -y_back); poly = clip(poly, side, 0, x_out)
        poly = clip(poly, -side, 0, 0.0)
        if len(poly) >= 3:
            add_prism(bm, poly, Z_BOT, Z_TOP, ia); info["diagonales"] += 1
    # travesano superior
    z_ts0 = Z_TS0
    for g in tsup:
        yc = (g[2] + g[3]) / 2
        zt = tray_min_z(g[0], g[1], yc - H, yc + H, ("Bandeja 2", "Bandeja 3"))
        z1 = (zt - 0.0005) if zt else g[5]; z0 = z1 - S; z_ts0 = z0; Z_TS0 = z0; TSUP_Y = (yc - H, yc + H)
        add_box(bm, g[0], g[1], yc - H, yc + H, z0, z1, ia)
        zl = tray_min_z(g[0], g[1], yc - H, yc + H, ("Bandeja 1", "Bandeja 4"))
        info["travesano_superior"] = {"z": [round(z0, 4), round(z1, 4)], "paso_huevos_mm": round((z0 - zl) * 1000, 1) if zl else None}
    # postes: crecen centrados; si chocan con algo, crecen desde una de sus caras viejas; si una bandeja
    # inclinada los toca por arriba, se bajan junto con su taco
    for g in posts:
        cx, cy = (g[0] + g[1]) / 2, (g[2] + g[3]) / 2
        xo = [(cx - H, cx + H), (g[0], g[0] + S), (g[1] - S, g[1])]
        yo = [(cy - H, cy + H), (g[2], g[2] + S), (g[3] - S, g[3])]
        for xi, a_, b_ in INNER_PLANES:          # pegado a un larguero: conserva esa cara, crece hacia adentro
            if b_ > g[2] and a_ < g[3]:
                if abs(g[1] - xi) < 0.001 and xi > 0: xo = [(xi - S, xi)]
                if abs(g[0] - xi) < 0.001 and xi < 0: xo = [(xi, xi + S)]
        z1 = g[5]
        if z_ts0 is not None and TSUP_Y and abs(cx) < 0.02 and TSUP_Y[0] - 0.01 < cy < TSUP_Y[1] + 0.01:
            z1 = z_ts0                               # poste central: hasta el travesano superior
        cands = sorted(((xx, yy) for xx in xo for yy in yo), key=lambda c: (xo.index(c[0]) > 0) + (yo.index(c[1]) > 0))
        pick = None
        for (x0, x1), (y0, y1) in cands:
            if not clash(x0, x1, y0, y1, g[4], z1): pick = (x0, x1, y0, y1); break
        lowered = 0.0
        if pick is None:                             # choca por arriba (bandeja inclinada): bajar poste + taco
            (x0, x1), (y0, y1) = cands[0]; pick = (x0, x1, y0, y1)
            tv = [v for v in bm.verts if any(f.material_index == ip for f in v.link_faces)
                  and abs(v.co.x - cx) < 0.0165 and abs(v.co.y - cy) < 0.0165 and g[5] - EPS <= v.co.z <= g[5] + 0.0065]
            th = (max(v.co.z for v in tv) - g[5]) if tv else 0.0
            zt = tray_min_z(cx - 0.0155, cx + 0.0155, cy - 0.0155, cy + 0.0155, TRAYS)
            if zt is not None:
                lowered = max(0.0, z1 - (zt - th - 0.0003))
                z1 -= lowered
                for v in tv: v.co.z -= lowered
                if clash(x0, x1, y0, y1, g[4], z1): report["avisos"].append(f"poste ({cx:.3f},{cy:.3f}) sigue tocando algo")
            if not o.name.startswith("Bastidor") and O.get(o.name + "_Taco") and lowered:
                TACO_SHIFT[o.name + "_Taco"] = lowered
        x0, x1, y0, y1 = pick
        add_box(bm, x0, x1, y0, y1, g[4], z1, ia)
        info["postes"].append([round((x0 + x1) / 2, 4), round((y0 + y1) / 2, 4), round(g[4], 4), round(z1, 4)] + ([f"bajado {lowered*1000:.1f} mm"] if lowered else []))
    # largueros traseros: hasta la cara trasera del travesano de remate
    # cartelas PETG bajo el travesano superior
    if ip is not None and z_ts0 is not None:
        nc = 0
        for f in [f for f in bm.faces if f.material_index == ip]:
            b = fb(f)
            if b[2][0] > 0.09 and b[2][1] < 0.125 and b[0][1] - b[0][0] < 0.05 and TSUP_Y and TSUP_Y[0] - 0.01 < (b[1][0] + b[1][1]) / 2 < TSUP_Y[1] + 0.01:
                for v in f.verts:
                    if abs(abs(v.co.x) - 0.010) < 0.0006: v.co.x = math.copysign(H, v.co.x)
                    if v.co.z > z_ts0: v.co.z = z_ts0
                nc += 1
        info["caras_cartela_ajustadas"] = nc
    # restos del empalme viejo (caras de aluminio en la base vieja de 20 mm, z 0.0339)
    junk = [f for f in bm.faces if f.material_index == ia and any(abs(v.co.z - (Z_TOP - 0.020)) < EPS for v in f.verts)]
    if junk:
        bmesh.ops.delete(bm, geom=junk, context='FACES')
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
        info["restos_borrados"] = len(junk)
    newf = [f for f in bm.faces if f.material_index == ia and not in_tube(f)]
    if newf: bmesh.ops.recalc_face_normals(bm, faces=newf)
    put(o, bm)
    return info

T0_REAR = None; Z_TS0 = None; TSUP_Y = None; TACO_SHIFT = {}
TRAYS = ("Bandeja 1", "Bandeja 2", "Bandeja 3", "Bandeja 4")
_dg = bpy.context.evaluated_depsgraph_get()
def _bvh(o):
    oe = o.evaluated_get(_dg); me = oe.to_mesh(); b = bmesh.new(); b.from_mesh(me); oe.to_mesh_clear()
    b.transform(o.matrix_world); t = BVHTree.FromBMesh(b); b.free(); return t
OTHERS = [_bvh(o) for o in vl.objects if o.type == 'MESH' and o.visible_get() and o != J and not o.name.startswith("Huevo")]
def clash(x0, x1, y0, y1, z0, z1):
    b = bmesh.new(); g = bmesh.ops.create_cube(b, size=1.0); k = 0.0003
    bmesh.ops.scale(b, verts=g['verts'], vec=(x1 - x0 - 2 * k, y1 - y0 - 2 * k, z1 - z0 - 2 * k))
    bmesh.ops.translate(b, verts=g['verts'], vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    t = BVHTree.FromBMesh(b); b.free()
    return any(t.overlap(u) for u in OTHERS)
report["copia_unida"] = convert(J, True)
HID = ["Bastidor_Travesanos_2020", "Bastidor_Largueros_2020.001", "Calza_Bandeja_Inf_atras_der", "Calza_Bandeja_Inf_atras_izq",
       "Poste_Bandeja_Sup_der", "Poste_Bandeja_Sup_izq", "Poste_Canaleta_atras", "Poste_Canaleta_media", "Poste_Central_Bandejas",
       "Poste_Pedestal_atras_der", "Poste_Pedestal_atras_izq", "Poste_Pedestal_frente_der", "Poste_Pedestal_frente_izq",
       "Travesano_Bandejas_Superiores_2020"]
for n in HID:
    if O.get(n): report[n] = convert(O[n], False)
# tacos sueltos ocultos que bajan con su poste
for n, d in TACO_SHIFT.items():
    t_ = O[n]; bm = wbm(t_)
    for v in bm.verts: v.co.z -= d
    put(t_, bm)
report["tacos_sueltos_bajados"] = {n: round(d * 1000, 1) for n, d in TACO_SHIFT.items()}
# cartelas sueltas ocultas
CT = O.get("Cartelas_Travesano"); ts = report["copia_unida"].get("travesano_superior") if report["copia_unida"] else None
if CT and ts:
    bm = wbm(CT)
    for v in bm.verts:
        if abs(abs(v.co.x) - 0.010) < 0.0006: v.co.x = math.copysign(H, v.co.x)
        if v.co.z > ts["z"][0]: v.co.z = ts["z"][0]
    put(CT, bm)

# ------------------------------------------------ revision: aluminio nuevo contra lo visible (encogido 0.3 mm)
dg = bpy.context.evaluated_depsgraph_get()
def bvh(o):
    oe = o.evaluated_get(dg); me = oe.to_mesh(); b = bmesh.new(); b.from_mesh(me); oe.to_mesh_clear()
    b.transform(o.matrix_world); t = BVHTree.FromBMesh(b); b.free(); return t
ia = slot(J, "Aluminio_2020"); bm = wbm(J)
for f in [f for f in bm.faces if f.material_index != ia]: pass
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != ia], context='FACES')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
# encoger cada pieza hacia su centro 0.3 mm
bm.verts.ensure_lookup_table(); seen = set()
for v in bm.verts:
    if v.index in seen: continue
    st = [v]; c = []; seen.add(v.index)
    while st:
        a = st.pop(); c.append(a)
        for e in a.link_edges:
            b = e.other_vert(a)
            if b.index not in seen: seen.add(b.index); st.append(b)
    cen = sum((q.co for q in c), Vector()) / len(c)
    for q in c:
        d = q.co - cen
        q.co -= Vector((math.copysign(0.0003, d.x) if abs(d.x) > 1e-5 else 0, math.copysign(0.0003, d.y) if abs(d.y) > 1e-5 else 0,
                        math.copysign(0.0003, d.z) if abs(d.z) > 1e-5 else 0))
TA = BVHTree.FromBMesh(bm); bm.free()
report["interferencias_aluminio"] = [o.name for o in vl.objects if o.type == 'MESH' and o.visible_get() and o != J
                                     and not o.name.startswith("Huevo") and TA.overlap(bvh(o))]
if "save" in argv:
    bpy.ops.wm.save_mainfile(); report["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(report))
