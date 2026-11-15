"""
Ovum1_9: moldes bipartidos (PLA) para colar las almohadillas de silicona del pesador y del girador.

Diseno de cada molde
  - Bloque alrededor de la almohadilla (paredes >= 6 mm) partido en dos mitades (A y B) por el plano vertical que
    pasa por el centro de la almohadilla, a lo largo de ella: corta tambien los pivotes por la mitad, asi las
    cabezas conicas salen de lado al abrir el molde (sin forzarlas por un agujero).
  - Se cuela por gravedad con la pieza en su posicion de uso: embudo en el extremo trasero (punto alto) y
    respiradero en el otro extremo. El techo de la cavidad es un arco concavo: el aire sube hacia los extremos.
  - Llaves conicas de alineacion (macho en A, hembra en B con 0.2 mm de juego) y 4 agujeros pasantes para M3.
  - STL en mm, ya orientados para imprimir: cara de particion hacia arriba, cara trasera plana en la cama.

Forma (desde 2026-11-06, por defecto "conforme"): el bloque sigue el perfil lateral de la almohadilla con W_CONF de
pared, en vez de ser una caja; los tornillos y las llaves van en orejas redondas pegadas al contorno. forma=caja
vuelve al bloque rectangular anterior.
Uso:  blender --background Ovum1_9.blend --python moldes_silicona_ovum1_9.py [-- save] [forma=caja]
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
O = bpy.data.objects; sc = bpy.context.scene
PADS = ["Silicona_Pesador_Izq", "Silicona_Pesador_Der", "Silicona_Girador_Izq", "Silicona_Girador_Der"]
MX, MY, MZ_BOT, MZ_TOP = 0.0065, 0.0095, 0.0055, 0.0055   # paredes del bloque (lateral, extremos, abajo, arriba)
SPRUE_TOP_D, SPRUE_D, SPRUE_L = 0.0090, 0.0035, 0.0045     # embudo: boca, garganta, largo del cono
VENT_D = 0.0020
KEY_D, KEY_H, KEY_GAP = 0.0050, 0.0030, 0.0002              # llave conica y juego de la hembra
BOLT_D = 0.0044                                              # paso M3 con holgura (3.4 mm en Ovum1_9 quedaba justo)
MIN_WALL = 0.0020                                            # distancia minima de llaves/tornillos a la cavidad
X_SHOW, X_STEP, GAP_SHOW = 0.42, 0.075, 0.010                # donde se muestran los moldes en la escena
CONF = not any(a == "forma=caja" for a in argv)              # molde conforme (minimo material)
W_CONF = 0.0040                                              # pared alrededor de la cavidad (perfil lateral)
MX_CONF = 0.0040                                             # pared lateral (a cada lado de la almohadilla, en x)
LUG_R = BOLT_D / 2 + 0.0030                                  # oreja de tornillo
KLUG_R = KEY_D / 2 + KEY_GAP + 0.0025                        # oreja de llave
LUG_SOLAPE = 0.0015                                          # cuanto entran las orejas en el contorno
report = {"moldes": {}, "avisos": []}

col = bpy.data.collections.get("Moldes_Silicona")
if not col:
    col = bpy.data.collections.new("Moldes_Silicona"); sc.collection.children.link(col)
for o in list(col.objects):
    me = o.data; bpy.data.objects.remove(o, do_unlink=True)
    if me and me.users == 0: bpy.data.meshes.remove(me)

def mat(name, col_, rough=0.5):
    m = bpy.data.materials.get(name)
    if m: return m
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF"); b.inputs["Base Color"].default_value = (*col_, 1); b.inputs["Roughness"].default_value = rough
    m.diffuse_color = (*col_, 1); return m
M_A = mat("PLA_Molde_A", (0.95, 0.55, 0.15)); M_B = mat("PLA_Molde_B", (0.98, 0.80, 0.25))

def obj_from_bm(name, bm, material=None, link=True):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    if material: me.materials.append(material)
    o = bpy.data.objects.new(name, me)
    if link: col.objects.link(o)
    return o
def box_bm(x0, x1, y0, y1, z0, z1, bm=None):
    bm = bm or bmesh.new(); g = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=g['verts'], vec=(x1 - x0, y1 - y0, z1 - z0))
    bmesh.ops.translate(bm, verts=g['verts'], vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)); return bm
def cone_bm(bm, r1, r2, depth, center, axis, seg=32):
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r1, radius2=r2, depth=depth)
    rot = Vector((0, 0, 1)).rotation_difference(axis).to_matrix()
    bmesh.ops.rotate(bm, verts=g['verts'], cent=(0, 0, 0), matrix=rot)
    bmesh.ops.translate(bm, verts=g['verts'], vec=center)
def _closed(o):
    b_ = bmesh.new(); b_.from_mesh(o.data); r_ = all(e.is_manifold for e in b_.edges) and len(b_.faces) > 0; b_.free(); return r_
def _apply(target, operand, op):
    m_ = target.modifiers.new("b", 'BOOLEAN'); m_.operation = op; m_.object = operand; m_.solver = 'EXACT'
    m_.use_self = True             # tolera autointersecciones en los operandos
    bpy.context.view_layer.objects.active = target
    with bpy.context.temp_override(object=target, active_object=target):
        bpy.ops.object.modifier_apply(modifier=m_.name)
NUDGES = [Vector((0, 0, 0)), Vector((2.3e-5, 1.7e-5, 1.1e-5)), Vector((-3.1e-5, 2.9e-5, -1.9e-5)), Vector((4.7e-5, -3.3e-5, 2.7e-5)),
          Vector((-6.1e-5, -5.3e-5, 4.1e-5))]
def lathe_bm(bm, x, y, prof, seg=32):
    """solido de revolucion alrededor de un eje vertical: prof = [(z, r), ...] de abajo hacia arriba"""
    rings = []
    for z, r in prof:
        rings.append([bm.verts.new((x + r * math.cos(2 * math.pi * k / seg), y + r * math.sin(2 * math.pi * k / seg), z)) for k in range(seg)])
    bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(seg):
            bm.faces.new((r0[k], r0[(k + 1) % seg], r1[(k + 1) % seg], r1[k]))
def fill_cut(bm, edges, rep, name):
    """rellena la cara de particion: contorno exterior + contornos de la cavidad como huecos (regla par-impar)"""
    from mathutils.geometry import tessellate_polygon
    es = {e for e in edges if e.is_boundary}
    adj = {}
    for e in es:
        for v in e.verts: adj.setdefault(v, []).append(e)
    loops = []; used = set()
    for e0 in es:
        if e0 in used: continue
        loop = [e0.verts[0]]; cur_v = e0.verts[1]; used.add(e0); prev = e0
        while cur_v is not loop[0]:
            loop.append(cur_v)
            nxt = [e for e in adj.get(cur_v, []) if e not in used]
            if not nxt: break
            prev = nxt[0]; used.add(prev); cur_v = prev.other_vert(cur_v)
        if cur_v is loop[0] and len(loop) >= 3: loops.append(loop)
        else: rep["avisos"].append(f"{name}: contorno de corte abierto ({len(loop)} vertices)")
    if not loops: return
    def area(l):
        return abs(sum(l[k].co.y * l[(k + 1) % len(l)].co.z - l[(k + 1) % len(l)].co.y * l[k].co.z for k in range(len(l)))) / 2
    loops.sort(key=area, reverse=True)
    flat = [v for l in loops for v in l]
    tris = tessellate_polygon([[(v.co.y, v.co.z, 0.0) for v in l] for l in loops])
    for t in tris:
        try: bm.faces.new([flat[t[0]], flat[t[1]], flat[t[2]]])
        except ValueError: pass
    rep.setdefault("contornos_particion", {}).setdefault(name, []).append(len(loops))
def boolean(target, operand, op):
    """booleano exacto; si el resultado no queda cerrado se deshace y se reintenta moviendo el operando unas
    centesimas de mm (casos degenerados: aristas o vertices coincidentes)"""
    was = _closed(target); keep = target.data.copy(); base = operand.location.copy()
    for k, d in enumerate(NUDGES):
        operand.location = base + d
        _apply(target, operand, op)
        if not was or _closed(target):
            operand.location = base; bpy.data.meshes.remove(keep); return k
        old = target.data; target.data = keep.copy(); bpy.data.meshes.remove(old)
    operand.location = base; bpy.data.meshes.remove(keep)
    report["avisos"].append(f"booleano {op} sobre {target.name} con {operand.name}: no quedo cerrado")
    _apply(target, operand, op); return -1
def tmp(name, bm):
    o = obj_from_bm(name, bm, link=False); sc.collection.objects.link(o); return o
def drop(o):
    try: me = o.data
    except ReferenceError: return          # ya eliminado
    bpy.data.objects.remove(o, do_unlink=True)
    if me.users == 0: bpy.data.meshes.remove(me)
def stats(o):
    b = bmesh.new(); b.from_mesh(o.data); b.transform(o.matrix_world)
    r = {"manifold": all(e.is_manifold for e in b.edges), "vol_cm3": round(b.calc_volume() * 1e6, 2)}
    b.free(); return r

def self_x(o):
    b_ = bmesh.new(); b_.from_mesh(o.data); b_.faces.ensure_lookup_table(); t_ = BVHTree.FromBMesh(b_)
    n_ = sum(1 for i_, j_ in t_.overlap(t_) if i_ < j_ and not (set(b_.faces[i_].verts) & set(b_.faces[j_].verts)))
    b_.free(); return n_
def limpiar_almohadilla(o):
    """resuelve autointersecciones internas: union exacta (con use_self) con un tetraedro dentro de la pieza"""
    antes = self_x(o)
    if antes == 0: return [0, 0]
    b_ = bmesh.new(); b_.from_mesh(o.data); b_.normal_update()
    f0 = max(b_.faces, key=lambda f: f.calc_area()); c0 = f0.calc_center_median() - f0.normal * 0.0006; b_.free()
    tb = bmesh.new(); vs = [tb.verts.new(c0 + Vector(d) * 0.0002) for d in ((1, 0, 0), (-0.5, 0.87, 0), (-0.5, -0.87, 0), (0, 0, 1))]
    for f in ((0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)): tb.faces.new([vs[k] for k in f])
    bmesh.ops.recalc_face_normals(tb, faces=tb.faces)
    t_ = tmp("tmp_tetra", tb)
    t_.matrix_world = o.matrix_world.copy()          # el tetraedro esta en coordenadas locales de la pieza
    m_ = o.modifiers.new("limpieza", 'BOOLEAN'); m_.operation = 'UNION'; m_.object = t_; m_.solver = 'EXACT'; m_.use_self = True
    bpy.context.view_layer.objects.active = o
    with bpy.context.temp_override(object=o, active_object=o):
        bpy.ops.object.modifier_apply(modifier=m_.name)
    drop(t_)
    return [antes, self_x(o)]

for i, pname in enumerate(PADS):
    pad = O.get(pname)
    if not pad: report["avisos"].append(f"falta {pname}"); continue
    report.setdefault("autointersecciones_almohadilla", {})[pname] = limpiar_almohadilla(pad)
    # copia de la almohadilla, llevada a la zona de moldes (misma orientacion: z arriba = colada)
    pb = bmesh.new(); pb.from_mesh(pad.data); pb.transform(pad.matrix_world)
    ws = [v.co for v in pb.verts]
    bb = [[min(w[k] for w in ws), max(w[k] for w in ws)] for k in range(3)]
    off = Vector((X_SHOW + i * X_STEP - (bb[0][0] + bb[0][1]) / 2, -(bb[1][0] + bb[1][1]) / 2, 0.0))
    bmesh.ops.translate(pb, verts=pb.verts, vec=off)
    bb = [[bb[0][0] + off.x, bb[0][1] + off.x], [bb[1][0] + off.y, bb[1][1] + off.y], bb[2]]
    tree = BVHTree.FromBMesh(pb)
    P = tmp("tmp_pad", pb)
    XM = (bb[0][0] + bb[0][1]) / 2                       # plano de particion (centro de la almohadilla)
    X0, X1 = (bb[0][0] - MX_CONF, bb[0][1] + MX_CONF) if CONF else (bb[0][0] - MX, bb[0][1] + MX)
    Y0, Y1 = bb[1][0] - MY, bb[1][1] + MY
    Z0, Z1 = bb[2][0] - MZ_BOT, bb[2][1] + MZ_TOP

    def top_at(y):
        h = tree.ray_cast(Vector((XM, y, Z1 + 0.01)), Vector((0, 0, -1)))
        return h[0].z if h[0] else None
    # colada (extremo trasero) y respiradero (extremo delantero), centrados en el plano de particion;
    # se busca desde cada extremo hacia dentro el primer punto con cavidad debajo (las puntas son angostas)
    def high_point(y_end, step):
        """punto mas alto del techo de la cavidad en los ultimos 10 mm de un extremo (ahi se junta el aire),
        al menos 1.5 mm dentro del borde y con techo a ambos lados del canal"""
        best = (None, None)
        for k in range(8, 41):
            y = y_end + step * 0.00025 * k
            zs_ = [top_at(y + dy) for dy in (-0.0018, 0.0, 0.0018)]     # techo a ambos lados: el canal no roza paredes
            if None in zs_: continue
            if best[1] is None or zs_[1] > best[1] + 1e-5: best = (y, zs_[1])
        if best[0] is not None:          # 1.5 mm hacia el centro: el canal sale del techo, lejos de la pared del extremo
            y2 = best[0] + step * 0.0015; z2 = top_at(y2)
            if z2 is not None and abs(z2 - best[1]) < 0.0015: best = (y2, z2)
        return best
    ys, zs = high_point(bb[1][0], +1)
    yv, zv = high_point(bb[1][1], -1)
    def ceil_min(y, r):
        """techo mas bajo de la cavidad dentro del circulo del canal"""
        zz = [top_at(y + r * math.sin(a)) for a in [k * math.pi / 6 for k in range(12)]] + [top_at(y)]
        return min(z for z in zz if z is not None)
    # --- perfil lateral conforme (y, z): silueta de la almohadilla engrosada W_CONF, con mesetas en colada/respiradero
    ZS_TOP = ZV_TOP = Z1
    if CONF:
        from mathutils.geometry import tessellate_polygon
        xs_ = [bb[0][0] + 0.0002 + (bb[0][1] - bb[0][0] - 0.0004) * k / 10 for k in range(11)]
        paso = 0.0005; ny_ = int(round((bb[1][1] - bb[1][0] + 2 * W_CONF) / paso)) + 1
        Ys = [bb[1][0] - W_CONF + paso * k for k in range(ny_)]
        raw = {}
        for y in Ys:
            tz = []; bz = []
            for x_ in xs_:
                h1 = tree.ray_cast(Vector((x_, y, Z1 + 0.05)), Vector((0, 0, -1)))[0]
                h2 = tree.ray_cast(Vector((x_, y, Z0 - 0.05)), Vector((0, 0, 1)))[0]
                if h1: tz.append(h1.z)
                if h2: bz.append(h2.z)
            if tz and bz: raw[y] = (max(tz), min(bz))
        ry = sorted(raw)
        def dil(y, sgn):
            best = None
            for yy in ry:
                d = abs(yy - y)
                if d > W_CONF: continue
                v = raw[yy][0] + math.sqrt(W_CONF ** 2 - d * d) if sgn > 0 else raw[yy][1] - math.sqrt(W_CONF ** 2 - d * d)
                if best is None or (v > best if sgn > 0 else v < best): best = v
            return best
        TOP = {y: dil(y, 1) for y in Ys}; BOT = {y: dil(y, -1) for y in Ys}
        Ys = [y for y in Ys if TOP[y] is not None]
        # mesetas: la colada necesita SPRUE_L de embudo sobre el techo de la cavidad; el respiradero 2 mm
        def meseta(yc_, r_, zmin):
            zt = max([TOP[y] for y in Ys if abs(y - yc_) <= r_ + W_CONF] + [zmin])
            for y in Ys:
                if abs(y - yc_) <= r_ + 0.0025: TOP[y] = max(TOP[y], zt)
            return zt
        if zs is not None: ZS_TOP = meseta(ys, SPRUE_TOP_D / 2, zs + SPRUE_L + 0.0020)
        if zv is not None: ZV_TOP = meseta(yv, VENT_D / 2, zv + 0.0020)
        PERFIL = [Vector((y, TOP[y])) for y in Ys] + [Vector((y, BOT[y])) for y in reversed(Ys)]
        # simplificar (puntos casi alineados)
        def simpl(P, tol=0.00002):
            out = []
            for k in range(len(P)):
                a, b_, c = P[k - 1], P[k], P[(k + 1) % len(P)]
                e = c - a
                if e.length > 1e-9 and abs((b_ - a).x * e.y - (b_ - a).y * e.x) / e.length < tol: continue
                out.append(b_)
            return out
        PERFIL = simpl(PERFIL)
        # orejas: 2 tornillos sobre la U (cerca del centro) y 2 bajo los brazos; 2 llaves centradas arriba y abajo
        L_ = bb[1][1] - bb[1][0]; yc_ = (bb[1][0] + bb[1][1]) / 2
        def cerca(y): return min(Ys, key=lambda yy: abs(yy - y))
        LUGS = []
        for yy in (yc_ - 0.16 * L_, yc_ + 0.16 * L_):
            y_ = cerca(yy); LUGS.append(("tornillo", y_, TOP[y_] + LUG_R - LUG_SOLAPE, LUG_R))
        for yy in (bb[1][0] + 0.22 * L_, bb[1][1] - 0.22 * L_):
            y_ = cerca(yy); LUGS.append(("tornillo", y_, BOT[y_] - LUG_R + LUG_SOLAPE, LUG_R))
        y_ = cerca(yc_)
        LUGS.append(("llave", y_, TOP[y_] + KLUG_R - LUG_SOLAPE, KLUG_R)); LUGS.append(("llave", y_, BOT[y_] - KLUG_R + LUG_SOLAPE, KLUG_R))
        # patas: las orejas de abajo llegan todas al mismo nivel, asi el molde cerrado se para solo para colar
        Z_PIE = min(z_ - r_ for k_, y_, z_, r_ in LUGS if z_ < BOT[cerca(y_)])
        PATAS = [(y_, z_, r_) for k_, y_, z_, r_ in LUGS if z_ < BOT[cerca(y_)] and z_ - r_ > Z_PIE + 1e-5]
    def cuerpo_bm(hx0, hx1):
        """bmesh del bloque de una mitad (x de hx0 a hx1): caja o perfil conforme (las orejas se agregan aparte)"""
        if not CONF: return box_bm(hx0, hx1, Y0, Y1, Z0, Z1)
        bm_ = bmesh.new(); P_ = PERFIL
        if (sum(P_[i].x * P_[(i + 1) % len(P_)].y - P_[(i + 1) % len(P_)].x * P_[i].y for i in range(len(P_)))) < 0: P_ = list(reversed(P_))
        lo = [bm_.verts.new((hx0, q.x, q.y)) for q in P_]; hi = [bm_.verts.new((hx1, q.x, q.y)) for q in P_]
        for t_ in tessellate_polygon([[(q.x, q.y, 0.0) for q in P_]]):
            bm_.faces.new([lo[t_[2]], lo[t_[1]], lo[t_[0]]]); bm_.faces.new([hi[t_[0]], hi[t_[1]], hi[t_[2]]])
        n_ = len(P_)
        for i in range(n_): bm_.faces.new((lo[i], lo[(i + 1) % n_], hi[(i + 1) % n_], hi[i]))
        bmesh.ops.recalc_face_normals(bm_, faces=bm_.faces); return bm_
    def agregar_orejas(h, hx0, hx1):
        if not CONF: return
        ob_ = bmesh.new()
        for _, y_, z_, r_ in LUGS:
            cone_bm(ob_, r_, r_, (hx1 - hx0) - 0.00002, Vector(((hx0 + hx1) / 2, y_, z_)), Vector((1, 0, 0)), seg=32)
        for y_, z_, r_ in PATAS:   # oreja estirada hacia abajo hasta Z_PIE (forma de capsula)
            cone_bm(ob_, r_, r_, (hx1 - hx0) - 0.00002, Vector(((hx0 + hx1) / 2, y_, Z_PIE + r_)), Vector((1, 0, 0)), seg=32)
            g_ = bmesh.ops.create_cube(ob_, size=1.0)
            bmesh.ops.scale(ob_, verts=g_['verts'], vec=((hx1 - hx0) - 0.00004, 2 * r_, z_ - (Z_PIE + r_)))
            bmesh.ops.translate(ob_, verts=g_['verts'], vec=((hx0 + hx1) / 2, y_, (z_ + Z_PIE + r_) / 2))
        Lo = tmp("tmp_orejas", ob_); boolean(h, Lo, 'UNION'); drop(Lo)      # boolean() usa use_self: las orejas se solapan
    chans = []
    if zs is not None:
        zb = ceil_min(ys, SPRUE_D / 2) - 0.0008
        b1 = bmesh.new()          # colada + embudo en un solo solido de revolucion
        lathe_bm(b1, XM, ys, [(zb, SPRUE_D / 2), (ZS_TOP - SPRUE_L, SPRUE_D / 2), (ZS_TOP + 0.0005, SPRUE_TOP_D / 2 + 0.0005 * (SPRUE_TOP_D - SPRUE_D) / 2 / SPRUE_L)])
        chans.append(tmp("tmp_colada", b1))
    else: report["avisos"].append(f"{pname}: sin punto de colada")
    if zv is not None:
        zb = ceil_min(yv, VENT_D / 2) - 0.0008
        b3 = bmesh.new(); lathe_bm(b3, XM, yv, [(zb, VENT_D / 2), (ZV_TOP + 0.0005, VENT_D / 2)]); chans.append(tmp("tmp_respiradero", b3))
    else: report["avisos"].append(f"{pname}: sin respiradero")
    # cavidad = almohadilla + canales (un solo solido), y se resta del bloque una sola vez
    for c_ in chans: boolean(P, c_, 'UNION')
    report.setdefault("cavidad_cerrada", {})[pname] = _closed(P)
    _cb = bmesh.new(); _cb.from_mesh(P.data); _cb.transform(P.matrix_world); cav_tree = BVHTree.FromBMesh(_cb); _cb.free()
    def in_cavity(p_):
        votes = 0
        for d_ in (Vector((0.31, 0.52, 0.79)), Vector((-0.6, 0.2, 0.77)), Vector((0.1, -0.85, 0.5))):
            d_ = d_.normalized(); cnt = 0; org = p_.copy()
            for _ in range(40):
                hh = cav_tree.ray_cast(org, d_)
                if hh[0] is None: break
                cnt += 1; org = hh[0] + d_ * 1e-6
            votes += cnt % 2
        return votes >= 2
    blk = obj_from_bm("tmp_bloque", cuerpo_bm(X0, X1), link=False); sc.collection.objects.link(blk)
    boolean(blk, P, 'DIFFERENCE')
    report.setdefault("bloque_cerrado", {})[pname] = _closed(blk)

    # mitades
    halves = {}
    # llaves y tornillos: posiciones candidatas en la cara de particion, lejos de la cavidad
    def clear_of_cavity(y, z, r):
        # distancia a la cavidad completa (almohadilla + colada + respiradero), medida a lo largo de todo el eje
        dist = min((cav_tree.find_nearest(Vector((x_, y, z)))[3] or 1.0) for x_ in [X0 + (X1 - X0) * k / 8 for k in range(9)])
        return dist is not None and dist >= r + MIN_WALL
    if CONF:
        bolts = [(y_, z_) for k_, y_, z_, r_ in LUGS if k_ == "tornillo" and clear_of_cavity(y_, z_, BOLT_D / 2)]
        keys = [(y_, z_) for k_, y_, z_, r_ in LUGS if k_ == "llave" and clear_of_cavity(y_, z_, KEY_D / 2 + KEY_GAP)]
        if len(bolts) < 4: report["avisos"].append(f"{pname}: solo {len(bolts)} tornillos (oreja muy cerca de la cavidad)")
    else:
        bolt_c = [(Y0 + 0.0045, Z0 + 0.0045), (Y1 - 0.0045, Z0 + 0.0045), (Y0 + 0.0045, Z1 - 0.0045), (Y1 - 0.0045, Z1 - 0.0045)]
        bolts = [c for c in bolt_c if clear_of_cavity(c[0], c[1], BOLT_D / 2)]
        ymid = (Y0 + Y1) / 2
        key_c = [(ymid - 0.012, Z0 + 0.0040), (ymid + 0.016, Z0 + 0.0040), (ymid, Z1 - 0.0040), (Y0 + 0.0045, (Z0 + Z1) / 2), (Y1 - 0.0045, (Z0 + Z1) / 2)]
        keys = [c for c in key_c if clear_of_cavity(c[0], c[1], KEY_D / 2 + KEY_GAP)][:3]
    if len(keys) < 2: report["avisos"].append(f"{pname}: solo {len(keys)} llaves")
    def n_open(o):
        b_ = bmesh.new(); b_.from_mesh(o.data); n_ = sum(1 for e in b_.edges if not e.is_manifold); b_.free(); return n_
    def limpiar_mitad(o):
        """quita solapas de espesor cero que a veces deja el booleano (caras coincidentes con normales opuestas)"""
        b_ = bmesh.new(); b_.from_mesh(o.data)
        bmesh.ops.remove_doubles(b_, verts=b_.verts, dist=1e-6)
        groups = {}
        for f in b_.faces:
            groups.setdefault(frozenset(v.index for v in f.verts), []).append(f)
        kill = [f for fs in groups.values() if len(fs) > 1 for f in fs]
        if kill:
            bmesh.ops.delete(b_, geom=kill, context='FACES')
            bmesh.ops.delete(b_, geom=[v for v in b_.verts if not v.link_faces], context='VERTS')
        b_.to_mesh(o.data); o.data.update(); b_.free()
        return len(kill)
    def build(XC):
        hs = {}
        for tag, (hx0, hx1), m_ in (("A", (X0, XC), M_A), ("B", (XC, X1), M_B)):
            # cada mitad = su caja maciza menos la cavidad (la cavidad cruza la cara de particion)
            h = obj_from_bm(f"Molde_{pname}_{tag}", cuerpo_bm(hx0, hx1), m_, link=False)
            sc.collection.objects.link(h)               # los booleanos se evaluan en la coleccion de la escena
            agregar_orejas(h, hx0, hx1)
            boolean(h, P, 'DIFFERENCE'); hs[tag] = h
        kb = bmesh.new(); sb = bmesh.new()
        for y, z in keys:      # macho: sale de A (+x) hacia B; base 0.3 mm dentro de A para una union limpia
            cone_bm(kb, KEY_D / 2, 0.0012, KEY_H + 0.0003, Vector((XC + (KEY_H - 0.0003) / 2, y, z)), Vector((1, 0, 0)))
            cone_bm(sb, KEY_D / 2 + KEY_GAP, 0.0012 + KEY_GAP, KEY_H + KEY_GAP + 0.0003, Vector((XC + (KEY_H + KEY_GAP - 0.0003) / 2, y, z)), Vector((1, 0, 0)))
        K = tmp("tmp_llaves", kb); Sk = tmp("tmp_hembras", sb)
        boolean(hs["A"], K, 'UNION'); boolean(hs["B"], Sk, 'DIFFERENCE'); drop(K); drop(Sk)
        for y, z in bolts:          # un agujero por operacion
            b4 = bmesh.new(); cone_bm(b4, BOLT_D / 2, BOLT_D / 2, (X1 - X0) + 0.004, Vector(((X0 + X1) / 2, y, z)), Vector((1, 0, 0)), seg=24)
            Bo = tmp("tmp_tornillo", b4)
            for h in hs.values(): boolean(h, Bo, 'DIFFERENCE')
            drop(Bo)
        for h in hs.values():
            if not _closed(h): limpiar_mitad(h)
        return hs
    # plano de particion corrido unas decimas de mm del centro (evita coincidencias/tangencias con la cavidad);
    # si alguna mitad no queda cerrada se prueba otro desplazamiento y, si ninguno, se deja el mejor
    intentos = {}; n_av = len(report["avisos"]); best = None
    for XC_OFF in (0.00011, -0.00011, 0.00023, -0.00023, 0.00037, -0.00037):
        hs = build(XM + XC_OFF)
        nm = sum(n_open(h) for h in hs.values()); intentos[round(XC_OFF * 1000, 2)] = nm
        if nm == 0:
            halves = hs; best = XC_OFF; break
        for h in hs.values(): drop(h)
    if best is None:
        best = min(intentos, key=intentos.get) / 1000
        halves = build(XM + best)
    XC = XM + best
    del report["avisos"][n_av:]
    report.setdefault("particion", {})[pname] = {"desplazamiento_mm": round(best * 1000, 2), "aristas_abiertas_por_intento": intentos}
    for t_ in [P, blk] + chans: drop(t_)

    # verificacion: la cavidad reproduce la almohadilla (puntos dentro de la silicona no estan en el PLA)
    trees = {}
    for tag, h in halves.items():
        b = bmesh.new(); b.from_mesh(h.data); b.transform(h.matrix_world); trees[tag] = BVHTree.FromBMesh(b); b.free()
    def inside(t, p):
        d = Vector((0.31, 0.52, 0.79)).normalized(); cnt = 0; org = p.copy()
        for _ in range(40):
            hit = t.ray_cast(org, d)
            if hit[0] is None: break
            cnt += 1; org = hit[0] + d * 1e-6
        return cnt % 2 == 1
    pb2 = bmesh.new(); pb2.from_mesh(pad.data); pb2.transform(pad.matrix_world); bmesh.ops.translate(pb2, verts=pb2.verts, vec=off); pb2.normal_update()
    bad = 0; n_in = 0
    for f in pb2.faces:
        p = f.calc_center_median() - f.normal * 0.0004
        n_in += 1
        if inside(trees["A"], p) or inside(trees["B"], p): bad += 1
    pb2.free()
    for h in halves.values():                       # a su coleccion
        col.objects.link(h); sc.collection.objects.unlink(h)
    # separar las mitades para verlas en la escena
    halves["A"].location.x -= GAP_SHOW / 2; halves["B"].location.x += GAP_SHOW / 2
    _hb = [halves["A"].matrix_world @ v.co for v in halves["A"].data.vertices] + [halves["B"].matrix_world @ v.co for v in halves["B"].data.vertices]
    report["moldes"][pname] = {"bloque_mm": [round((X1 - X0) * 1000, 1)] + [round((max(w[k] for w in _hb) - min(w[k] for w in _hb)) * 1000, 1) for k in (1, 2)],
                               "forma": "conforme" if CONF else "caja",
                               "A": stats(halves["A"]), "B": stats(halves["B"]), "llaves": len(keys), "tornillos_M3": len(bolts),
                               "puntos_de_cavidad_ocupados": f"{bad}/{n_in}", "plano_particion_x_mm": round(XM * 1000, 2)}
    pv = bmesh.new(); pv.from_mesh(pad.data); pv.transform(pad.matrix_world)
    report["moldes"][pname]["silicona_cm3"] = round(pv.calc_volume() * 1e6, 2); pv.free()
    # colada y respiradero abiertos: un rayo desde arriba (junto al plano) llega hasta la cavidad sin tocar PLA
    for nm_, y_, z_ in (("colada_abierta", ys, zs), ("respiradero_abierto", yv, zv)):
        if z_ is None: continue
        ok_ = True
        for tag, t in trees.items():
            dx = -0.0004 if tag == "A" else 0.0004
            h_ = t.ray_cast(Vector((XM + dx, y_, Z1 + 0.01)), Vector((0, 0, -1)))
            if h_[0] is not None and h_[0].z > z_ + 0.0001: ok_ = False
        report["moldes"][pname][nm_] = ok_

# ---------------------------------------------------------------- STL orientados para imprimir (mm)
if "save" in argv:
    BASE = bpy.path.display_name_from_filepath(bpy.data.filepath)
    outdir = os.path.join(os.path.dirname(bpy.data.filepath), "stl", "moldes" if BASE == "Ovum1_9" else f"moldes_{BASE}"); os.makedirs(outdir, exist_ok=True)
    files = []
    for h in list(col.objects):
        b = bmesh.new(); b.from_mesh(h.data); b.transform(h.matrix_world)
        # cara de particion hacia ARRIBA (cara trasera plana en la cama): la cavidad se imprime abierta, sin
        # soportes, y los agujeros de tornillo quedan verticales. A mira +x y B mira -x antes de rotar.
        ang = math.radians(-90) if h.name.endswith("_A") else math.radians(90)
        bmesh.ops.rotate(b, verts=b.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(ang, 3, 'Y'))
        zmin = min(v.co.z for v in b.verts); xs = [v.co.x for v in b.verts]; ys = [v.co.y for v in b.verts]
        bmesh.ops.translate(b, verts=b.verts, vec=(-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -zmin))
        t = obj_from_bm("tmp_stl", b, link=False); sc.collection.objects.link(t)
        bpy.ops.object.select_all(action='DESELECT'); t.select_set(True); bpy.context.view_layer.objects.active = t
        fp = os.path.join(outdir, f"{h.name}.stl")
        bpy.ops.wm.stl_export(filepath=fp, export_selected_objects=True, global_scale=1000.0)
        files.append(os.path.basename(fp)); drop(t)
    # almohadillas limpias (sin autointersecciones) tambien se reexportan
    for pname in PADS:
        pad = O.get(pname)
        if not pad: continue
        bpy.ops.object.select_all(action='DESELECT'); pad.select_set(True); bpy.context.view_layer.objects.active = pad
        fp = os.path.join(os.path.dirname(outdir), f"{BASE}_{pname}.stl")
        bpy.ops.wm.stl_export(filepath=fp, export_selected_objects=True, global_scale=1000.0)
        files.append("../" + os.path.basename(fp))
    report["stl"] = files
    bpy.ops.wm.save_mainfile(); report["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(report))
