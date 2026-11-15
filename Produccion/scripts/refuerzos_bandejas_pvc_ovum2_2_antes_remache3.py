"""
Ovum2_2: refuerzos imprimibles (PETG) para las bandejas de PVC de 2 mm.
Las escuadras bajo el piso no alcanzan para dar rigidez; se agregan:
  - Esquineros: postes en L/V por fuera de cada esquina de pared (pliegue o union entre piezas), de toda la
    altura de la pared, con agujeros para insertos de laton M3 (el tornillo entra desde adentro de la bandeja).
  - Perfiles de borde: angulo en L que tapa el canto superior de las paredes y baja por la cara exterior.
  - Nervios bajo el piso: barras de 3 x 8 mm pegadas bajo el piso, solo donde abajo hay lugar
    (contra las bandejas inferiores se reserva el alto de un huevo).
Nada va por dentro (donde ruedan los huevos) y nada cuelga donde ruedan los huevos de abajo.

La geometria de las bandejas sale de alucobond_bandejas_ovum1_9.py (mat=pvc), que se ejecuta hasta los solidos.
Uso:  blender --background Ovum2_2.blend --python refuerzos_bandejas_pvc_ovum2_2.py -- [out <dir>] [blend <copia.blend>]
Salida: STL por pieza en stl/refuerzos_bandejas_pvc, lista de piezas, y (con blend) una copia del .blend con
la coleccion PETG_Refuerzos_Bandejas. No sobrescribe el .blend abierto.

2026-11-12 (zocalo LDown_9 con geometria rara): cada zocalo sale como UN solo cuerpo cerrado.
  - el ala exterior entra 1 mm en el ala bajo el piso (antes se tocaban solo por una arista: cuna sin material)
  - el esquinero se funde con un boolean UNION (antes join: dos cuerpos encimados)
  - toda pieza se funde aunque no lleve tornillos
  - el control de choques confirma por muestreo de puntos los choques entre refuerzos (el encogido de 0.15 mm
    daba falsos positivos en las medias maderas y quitaba piezas buenas); los choques con el PVC siguen igual
  - al final pasa reparar_zocalos_ovum2_2.py (cunas, medias maderas apoyadas cara con cara)
  OJO al volver a correrlo sobre un .blend que ya tiene zocalos: ocultarlos antes, si no cuentan como obstaculo.
"""
import bpy, bmesh, sys, os, math, json
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
BASE = os.path.dirname(bpy.data.filepath)
REF_OUT = ARGS[ARGS.index("out") + 1] if "out" in ARGS else os.path.join(BASE, "stl", "refuerzos_bandejas_pvc")
TMP = os.path.join(os.environ.get("TEMP", BASE), "ovum_refuerzos_tmp")
os.makedirs(REF_OUT, exist_ok=True); os.makedirs(TMP, exist_ok=True)

# geometria de las bandejas (PVC) desde el script de bandejas, sin escribir sus DXF
_src = open(os.path.join(BASE, "scripts", "alucobond_bandejas_ovum1_9.py"), encoding="utf-8").read()
_src = _src.replace('argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []', 'argv = ["mat=pvc", "out", r"%s"]' % TMP)
_src = _src[:_src.index("# ------------------------------------------------------------------ DXF, SVG, herrajes")]
exec(_src)

# ------------------------------------------------------------------ parametros (mm)
PT = 4.0          # espesor del esquinero (deja meter el inserto M3)
LEG = 16.0        # largo de cada ala del esquinero sobre la cara exterior
R_INS = 2.0       # agujero D4.0 para inserto termico M3 (largo 4 mm)
CAP_T = 2.5       # espesor del perfil de borde
CAP_LEG = 10.0    # alto del ala exterior del perfil de borde
CAP_MAX = 180.0   # largo maximo de una pieza impresa
RIB_W, RIB_H = 3.0, 8.0
RIB_PASO = 60.0
RIB_INSET = 26.0  # los nervios quedan lejos de las paredes y de las escuadras
EGG_H = 45.0      # alto de un huevo acostado (holgura sobre los pisos de las bandejas de abajo)
LUZ = 4.0         # luz minima bajo un nervio
MINANG = 8.0      # esquinas menores no llevan esquinero (las cubre el perfil de borde)
AV = []
def av(s): AV.append(s)

def prism(bm, pts, z0, z1):
    """prisma vertical de un poligono en planta (ccw) entre z0 y z1 (pueden variar por vertice)"""
    n = len(pts)
    zl = list(z0) if isinstance(z0, list) else [z0] * n; zh = list(z1) if isinstance(z1, list) else [z1] * n
    if area2(pts) < 0: pts = list(reversed(pts)); zl.reverse(); zh.reverse()
    lo = [bm.verts.new((p.x, p.y, zl[i])) for i, p in enumerate(pts)]; hi = [bm.verts.new((p.x, p.y, zh[i])) for i, p in enumerate(pts)]
    bm.faces.new(list(reversed(lo))); bm.faces.new(hi)
    for i in range(n): bm.faces.new((lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i]))
def cyl(bm, c, d, r, L):
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=r, radius2=r, depth=L)
    bmesh.ops.rotate(bm, verts=g['verts'], cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(d).to_matrix())
    bmesh.ops.translate(bm, verts=g['verts'], vec=c)
def to_obj(name, bm, coll, mat_):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob); me.materials.append(mat_)
    return ob
def boolean_diff(ob, cutter_bm):
    me2 = bpy.data.meshes.new("cut"); cutter_bm.to_mesh(me2); cutter_bm.free()
    b = bpy.data.objects.new("cut", me2); bpy.context.scene.collection.objects.link(b)
    md = ob.modifiers.new("d", 'BOOLEAN'); md.operation = 'DIFFERENCE'; md.object = b; md.solver = 'EXACT'
    md.use_self = True; md.use_hole_tolerant = True        # la pieza son prismas solapados: unirlos al restar
    with bpy.context.temp_override(object=ob, active_object=ob): bpy.ops.object.modifier_apply(modifier=md.name)
    bpy.data.objects.remove(b, do_unlink=True); bpy.data.meshes.remove(me2)

coll = bpy.data.collections.get("PETG_Refuerzos_Bandejas") or bpy.data.collections.new("PETG_Refuerzos_Bandejas")
if coll.name not in [c.name for c in bpy.context.scene.collection.children]: bpy.context.scene.collection.children.link(coll)
for ob in list(coll.objects): bpy.data.objects.remove(ob, do_unlink=True)
matR = bpy.data.materials.get("PETG_Refuerzo") or bpy.data.materials.new("PETG_Refuerzo"); matR.diffuse_color = (0.2, 0.75, 0.35, 1.0)

PIEZAS = []      # dict(nombre, tipo, obj, tray, info)
def sz(pc, s): return z_at(pc["bot"], s), z_at(pc["top"], s)
def s_at(seg, X): return seg["S"] + seg["a0"] + (X - v2(seg["C0"])).dot(seg["d"])
def clips_on(seg):
    return [(v2(c["Jbo"]) - v2(seg["C0"])).dot(seg["d"]) for c in CLIPS if c["tab"].get("rec") is seg["rec"]]

_dg0 = bpy.context.evaluated_depsgraph_get()
def libre(P, dirz, own, maxd=60.0):
    """distancia libre desde P (mm) en vertical, ignorando la propia bandeja"""
    org = P / 1000.0; dz = Vector((0, 0, dirz)); tot = 0.0
    for _ in range(25):
        ok, loc, nrm, i_, ob, m_ = _sc.ray_cast(_dg0, org, dz, distance=(maxd - tot) / 1000.0)
        if not ok: return 1e9
        d_ = (org - loc).length * 1000.0 + tot
        if ob.name.startswith(own) or ob.name.startswith(("Huevo", "BandejaCentral", "BandejaL", "BandejaR")) or coll in ob.users_collection:
            tot = d_ + 0.2; org = loc + dz * 0.0002
            if tot >= maxd: return 1e9
            continue
        return d_
    return 1e9
def own_of(tr): return (f"PVC_{tr.name}_", f"PETG_Escuadras_{tr.name}", f"PETG_Cuna_{tr.name}", f"PETG_Separador_{tr.name}")

# ------------------------------------------------------------------ esquineros
POSTS = {}       # (id(seg), extremo) -> largo de ala usado
POST_AT = {}     # (id(seg que llega), id(seg que sale)) -> nombre del esquinero
POST_INS = {}    # nombre del esquinero -> insertos M3
for tr in TR.values():
    R = tr.recs; n = len(R)
    for i in range(n):
        r0, r1 = R[i], R[(i + 1) % n]
        if not (r0["wall"] and r1["wall"] and r0["kind"] == "own" and r1["kind"] == "own"): continue
        p0, s0 = seg_of(tr, r0); p1, s1 = seg_of(tr, r1)
        if s0 is None or s1 is None or (v2(s0["C1"]) - v2(s1["C0"])).length > 1.0: continue
        th = math.degrees(math.acos(max(-1, min(1, s0["d"].dot(s1["d"])))))
        if th < MINANG: continue
        if r0.get("gapwall") or r1.get("gapwall"): continue          # sin lugar por fuera
        if any(shared_partner(tr, rr, v2(ss["C0"]) + ss["d"] * u) is not None
               for rr, ss in ((r0, s0), (r1, s1)) for u in (2.0, min(20.0, ss["L"] - 2.0), max(0.0, ss["L"] - 20.0), ss["L"] - 2.0)):
            continue                                                  # al lado hay piso de otra bandeja
        C = v2(s0["C1"]); d0, d1, n0, n1 = s0["d"], s1["d"], s0["n"], s1["n"]
        O = line_x(C + n0 * T, d0, C + n1 * T, d1) or (C + (n0 + n1) * (T / 2))
        Q = line_x(O + n0 * PT, d0, O + n1 * PT, d1) or (O + (n0 + n1).normalized() * PT)
        # alas: no pisar escuadras ni salir del tramo
        L0, L1 = min(LEG, s0["L"] - 3.0), min(LEG, s1["L"] - 3.0)
        if min(L0, L1) < 6.0: continue
        cerca = any(dist < LEG + W_TAB / 2 + 2 for dist in [s0["L"] - u for u in clips_on(s0)] + clips_on(s1))
        poly = [O - d0 * L0, O - d0 * L0 + n0 * PT, Q, O + d1 * L1 + n1 * PT, O + d1 * L1, O]
        if abs(area2(poly)) < 1.0: continue
        zb0, zt0 = sz(p0, s0["S"] + s0["flat"]); zb1, zt1 = sz(p1, s1["S"] + s1["a0"])
        z0, z1 = max(zb0, zb1), min(zt0, zt1)
        if z1 - z0 < 10.0: continue
        bm = bmesh.new(); prism(bm, poly, z0, z1)
        ob = to_obj(f"PETG_Esquinero_{tr.name}_{len([p for p in PIEZAS if p['tray'] == tr.name and p['tipo'] == 'esquinero']) + 1}", bm, coll, matR)
        # agujeros para insertos M3: centro de cada ala, alturas con luz para la cabeza del tornillo (lado huevo)
        concava = d1.dot(n0) < 0
        zf = max(zb0, zb1) + T / max(tr.G[r0["g"]]["n"].z, 0.3)          # cara superior del piso
        hs = [h for h in (6.0, (z1 - zf) - 6.0) if 5.0 <= h <= z1 - zf - 4.0 and zf + h - 4.0 >= z0 and (concava or egg_clear(h) >= 2.5)]
        hs = sorted(set(round(h, 1) for h in hs))
        if len(hs) == 2 and hs[1] - hs[0] < 8: hs = hs[:1]
        cut = bmesh.new()
        for (dd, nn, LL) in ((-d0, n0, L0), (d1, n1, L1)):
            for h in hs:
                c3 = Vector(((O + dd * (LL / 2)).x, (O + dd * (LL / 2)).y, zf + h)) + Vector((nn.x, nn.y, 0)) * (PT / 2)
                cyl(cut, c3, Vector((nn.x, nn.y, 0)), R_INS, PT + 2)
        if hs: boolean_diff(ob, cut)
        else: cut.free()
        POSTS[(id(s0), 1)] = L0; POSTS[(id(s1), 0)] = L1
        POST_AT[(id(s0), id(s1))] = ob.name; POST_INS[ob.name] = 2 * len(hs)
        PIEZAS.append(dict(nombre=ob.name, tipo="esquinero", obj=ob, tray=tr.name,
                           info=f"esquina de {th:.0f} grados, alto {z1 - z0:.0f} mm, {2 * len(hs)} insertos M3"))

# ------------------------------------------------------------------ zocalos: escuadras continuas unidas entre si
# Angulo en L (CT) por fuera y bajo el piso a lo largo de todo el borde inferior de cada pared propia: ala bajo el
# piso de HH desde la cara exterior del zocalo, ala exterior de HV desde la cara inferior del zocalo. Dobla las
# esquinas a inglete y se funde con el esquinero. Las piezas (<= RMAX) se unen a media madera sobre un tornillo M3
# de los que ya tenian las escuadras (mismos agujeros en el PVC).
CT = 3.0; HV = CLIP_V; HH = CLIP_H; LAP = 16.0; RMAX = 180.0; PASO_Z = 2.0
def fb_at(tr, g, X, g2=None):
    """cara superior del zocalo: 0.3 bajo el piso; cerca de un pliegue sigue al plano mas bajo"""
    gs = {g} | ({g2} if g2 is not None else set())
    if inside2(X, tr.corners): gs.add(floor_g(tr, X))       # solo caras de piso que estan de verdad sobre ese punto
    return min(zbot(tr, k, X) for k in gs) - 0.3          # cara superior del zocalo (bajo el piso)
def offline(seg, o): return v2(seg["C0"]) + seg["n"] * o, seg["d"]
def ends(segA, segB, o):
    """punto de inglete entre la linea de segA y la de segB a la distancia o de la cara interior"""
    pa, da = offline(segA, o); pb, db = offline(segB, o)
    return line_x(pa, da, pb, db) if abs(cross2(da, db)) > 0.02 else None
def quad_u(seg, u0, u1, oa, ob, prev=None, nxt=None):
    """cuadrilatero en planta del tramo [u0,u1] entre las paralelas a distancia oa y ob; inglete con prev/nxt"""
    C0, d, n = v2(seg["C0"]), seg["d"], seg["n"]
    A = [C0 + d * u0 + n * oa, C0 + d * u0 + n * ob]; B = [C0 + d * u1 + n * oa, C0 + d * u1 + n * ob]
    if prev is not None:
        x = [ends(prev, seg, o) for o in (oa, ob)]
        if all(x): A = x
    if nxt is not None:
        x = [ends(seg, nxt, o) for o in (oa, ob)]
        if all(x): B = x
    return [A[0], B[0], B[1], A[1]]
def add_tramo(bm, tr, seg, u0, u1, banda, prev=None, nxt=None):
    """banda: 'full', 'int' (mitad contra la pared/piso) o 'ext' (mitad de afuera/abajo)"""
    g = seg["rec"]["g"]; nz = max(tr.G[g]["n"].z, 0.3)
    hv = {"full": (T + 0.2, T + 0.2 + CT), "int": (T + 0.2, T + 0.1 + CT / 2), "ext": (T + 0.3 + CT / 2, T + 0.2 + CT)}[banda]
    hh = {"full": (0.0, CT), "int": (0.0, CT / 2 - 0.1), "ext": (CT / 2 + 0.1, CT)}[banda]      # 0.2 mm de juego en la media madera
    # ala bajo el piso (incluye el bloque bajo el ala exterior)
    q = quad_u(seg, u0, u1, T + 0.2 + CT - HH, T + 0.2 + CT, prev, nxt)
    esq = [(v2(seg["C0"]), prev["rec"]["g"])] if prev is not None else []
    if nxt is not None: esq.append((v2(seg["C1"]), nxt["rec"]["g"]))
    def g2_at(p):        # la cara de piso de la pared vecina solo cuenta cerca de la esquina
        c_ = [gg for C_, gg in esq if (p - C_).length < 30.0]
        return c_[0] if c_ else None
    top = [fb_at(tr, g, p, g2_at(p)) - hh[0] / nz for p in q]; bot = [fb_at(tr, g, p, g2_at(p)) - hh[1] / nz for p in q]
    prism(bm, q, bot, top)
    # ala exterior (sobre la cara superior del zocalo)
    q2 = quad_u(seg, u0, u1, hv[0], hv[1], prev, nxt)
    zb = [fb_at(tr, g, p, g2_at(p)) for p in q2]; zt = [z + HV - CT for z in zb]
    if banda == "full": zb = [z - 1.0 / nz for z in zb]     # solapa con el ala de abajo (sin cara de contacto)
    prism(bm, q2, zb, zt)
def tramo_slice_ok(tr, seg, u, own_bvh_skip):
    b = bmesh.new(); add_tramo(b, tr, seg, max(0.0, u - 1.0), min(seg["L"], u + 1.0), "full")
    b.normal_update()
    for v in b.verts: v.co -= v.normal * 0.15
    t = BVHTree.FromBMesh(b); b.free()
    return next((nm for nm, bv in ZOC_OBS.items() if t.overlap(bv)), None)
# obstaculos: todo lo visible menos las escuadras sueltas (se reemplazan), refuerzos y huevos
def bvh_scene(o, shrink=0.1):
    oe = o.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = oe.to_mesh(); b = bmesh.new(); b.from_mesh(me); oe.to_mesh_clear()
    b.transform(Matrix.Scale(1000.0, 4) @ o.matrix_world); b.normal_update()
    for v in b.verts: v.co -= v.normal * shrink
    t = BVHTree.FromBMesh(b); b.free(); return t
ZOC_OBS = {o.name: bvh_scene(o) for o in bpy.context.view_layer.objects
           if o.type == 'MESH' and o.visible_get() and coll not in o.users_collection
           and not o.name.startswith(("Huevo", "tmp", "PETG_Escuadras", "PETG_Borde"))}
ZOC = []          # dict(tray, obj, segs, clips cubiertas)
CUBIERTAS = set() # id(clip) reemplazadas por un zocalo
ZOC_CLIPS = {}    # zocalo -> clips que reemplaza
for tr in TR.values():
    R = tr.recs; n = len(R)
    # cadenas de paredes propias consecutivas
    start = next((i for i, r in enumerate(R) if not (r["wall"] and r["kind"] == "own")), 0)
    chains = []; cur = []
    for k in range(1, n + 1):
        r = R[(start + k) % n]; pc, sg = seg_of(tr, r) if (r["wall"] and r["kind"] == "own") else (None, None)
        if sg is not None and (not cur or (v2(cur[-1][1]["C1"]) - v2(sg["C0"])).length < 1.0): cur.append((pc, sg)); continue
        if cur: chains.append(cur)
        cur = [(pc, sg)] if sg is not None else []
    if cur: chains.append(cur)
    for ch in chains:
        # coordenada de recorrido y validez cada PASO_Z mm
        P0 = []; acc = 0.0
        for pc, sg in ch: P0.append(acc); acc += sg["L"]
        oks = []
        for k, (pc, sg) in enumerate(ch):
            r = sg["rec"]; u = 0.0
            while u <= sg["L"] + 1e-6:
                X = v2(sg["C0"]) + sg["d"] * u
                ok = not r.get("gapwall") and shared_partner(tr, r, X) is None and tramo_slice_ok(tr, sg, u, None) is None
                oks.append((P0[k] + u, ok)); u += PASO_Z
        ivs = []; a = None
        for p, ok in oks:
            if ok and a is None: a = p
            if not ok and a is not None:
                if p - PASO_Z - a > 30: ivs.append([a, p - PASO_Z])
                a = None
        if a is not None and oks[-1][0] - a > 30: ivs.append([a, oks[-1][0]])
        # tornillos (escuadras actuales) sobre la cadena
        scr = []
        for k, (pc, sg) in enumerate(ch):
            for c in CLIPS:
                if c["tab"].get("rec") is sg["rec"]:
                    scr.append((P0[k] + (v2(c["Jbo"]) - v2(sg["C0"])).dot(sg["d"]), c, k))
        scr.sort(key=lambda x: x[0])
        esquinas = P0[1:]
        for a, b in ivs:
            a += 0.5; b -= 0.5
            cortes = []; st = a
            while b - st > RMAX:
                cand = [x for x in scr if st + 40 < x[0] < st + RMAX - LAP / 2 and all(abs(x[0] - e) > 25 for e in esquinas)]
                if cand: c_ = max(cand, key=lambda x: x[0]); cortes.append((c_[0], True)); st = c_[0] - LAP / 2
                else: cortes.append((st + RMAX, False)); st = st + RMAX; av(f"{tr.name}: zocalo cortado sin tornillo de union en {st:.0f}")
            # tramos de cada pieza en coordenada de recorrido con su banda
            bordes = [(a, None)] + cortes + [(b, None)]
            for j in range(len(bordes) - 1):
                (pa, la), (pb, lb) = bordes[j], bordes[j + 1]
                partes = []
                if la: partes.append((pa - LAP / 2, pa + LAP / 2, "ext")); lo = pa + LAP / 2
                else: lo = pa
                if lb: partes.append((lo, pb - LAP / 2, "full")); partes.append((pb - LAP / 2, pb + LAP / 2, "int"))
                else: partes.append((lo, pb, "full"))
                bm = bmesh.new(); segs_usados = set()
                for q0, q1, banda in partes:
                    for k, (pc, sg) in enumerate(ch):
                        u0, u1 = max(q0, P0[k]) - P0[k], min(q1, P0[k] + sg["L"]) - P0[k]
                        if u1 - u0 < 0.05: continue
                        prev = ch[k - 1][1] if k > 0 and u0 < 0.05 and q0 < P0[k] - 0.05 else None
                        nxt = ch[k + 1][1] if k + 1 < len(ch) and u1 > sg["L"] - 0.05 and q1 > P0[k] + sg["L"] + 0.05 else None
                        add_tramo(bm, tr, sg, u0, u1, banda, prev, nxt); segs_usados.add(k)
                nm = f"PETG_Zocalo_{tr.name}_{len([z for z in ZOC if z['tray'] == tr.name]) + 1}"
                ob = to_obj(nm, bm, coll, matR)
                # agujeros M3 pasantes de las escuadras que este zocalo reemplaza
                cut = bmesh.new(); ncl = 0; mis_clips = []
                for x, c, k in scr:
                    if pa - LAP / 2 - 0.1 <= x <= pb + LAP / 2 + 0.1 and (pa - 1 <= x <= pb + 1):
                        sg = ch[k][1]; pcw = ch[k][0]
                        cyl(cut, c["hole_piso"] - c["nf"] * (CT / 2 + 0.5), c["nf"], R_HOLE, CT + 4)
                        u = (v2(c["Jbo"]) - v2(sg["C0"])).dot(sg["d"]); Pw = v2(sg["C0"]) + sg["d"] * u + sg["n"] * (T + CT / 2)
                        cyl(cut, Vector((Pw.x, Pw.y, c["z_rem"])), Vector((sg["n"].x, sg["n"].y, 0)), R_HOLE, CT + 4)
                        CUBIERTAS.add(id(c)); ncl += 1; mis_clips.append(id(c))
                if not ncl:
                    cyl(cut, Vector((0.0, 0.0, -5000.0)), Vector((0, 0, 1)), 1.0, 1.0)   # cortador lejano: solo funde
                boolean_diff(ob, cut)
                # esquineros dentro de esta pieza: se funden
                fund = []
                for k in range(1, len(ch)):
                    if pa + 5 < P0[k] < pb - 5:
                        pn = POST_AT.get((id(ch[k - 1][1]), id(ch[k][1])))
                        if pn and pn in bpy.data.objects:
                            po = bpy.data.objects[pn]
                            md_ = ob.modifiers.new("u", 'BOOLEAN'); md_.operation = 'UNION'; md_.object = po; md_.solver = 'EXACT'
                            md_.use_self = True; md_.use_hole_tolerant = True
                            with bpy.context.temp_override(object=ob, active_object=ob): bpy.ops.object.modifier_apply(modifier=md_.name)
                            bpy.data.objects.remove(po, do_unlink=True); fund.append(pn)
                            for p_ in list(PIEZAS):
                                if p_["nombre"] == pn: PIEZAS.remove(p_)
                largo = pb - pa + (LAP / 2 if la else 0) + (LAP / 2 if lb else 0)
                nins = sum(POST_INS.get(x, 0) for x in fund)
                info = f"largo {largo:.0f} mm, {ncl} tornillos M3" + (f", con {len(fund)} esquinero(s), {nins} insertos M3" if fund else "")
                ZOC_CLIPS[ob.name] = mis_clips
                ZOC_OBS[ob.name] = BVHTree.FromObject(ob, bpy.context.evaluated_depsgraph_get())   # los siguientes zocalos lo esquivan
                ZOC.append(dict(tray=tr.name, obj=ob)); PIEZAS.append(dict(nombre=ob.name, tipo="zocalo", obj=ob, tray=tr.name, info=info))

# ------------------------------------------------------------------ nervios bajo el piso
_dg2 = bpy.context.evaluated_depsgraph_get()
def bajo(P, own):
    """distancia libre hacia abajo desde P (mm); contra pisos de otras bandejas se descuenta el alto del huevo"""
    org = P / 1000.0; left = 0.3; dz = Vector((0, 0, -1)); tot = 0.0
    for _ in range(20):
        ok, loc, nrm, i_, ob, m_ = _sc.ray_cast(_dg2, org, dz, distance=left)
        if not ok: return 1e9
        dist = (org - loc).length * 1000.0 + tot
        nm = ob.name
        if nm.startswith(own) or nm.startswith(("Huevo", "BandejaCentral", "BandejaL", "BandejaR", "PETG_Refuerzo", "PETG_Borde", "PETG_Esquinero")):
            tot = dist + 0.2; org = loc + dz * 0.0002; left = 0.3 - tot / 1000.0
            if left <= 0: return 1e9
            continue
        if nm.startswith("PVC_") and "Piso" in nm: return dist - EGG_H
        return dist
    return 1e9
NERVIOS = False   # el usuario los quito (2026-11-06)
for tr in (TR.values() if NERVIOS else []):
    own = (f"PVC_{tr.name}_", f"PETG_Escuadras_{tr.name}", f"PETG_Cuna_{tr.name}")
    for g, rg in tr.regions:
        G = tr.G[g]; nrm = G["n"]
        pts = rg
        # direccion principal del tramo de piso
        c = sum(pts, Vector((0, 0))) / len(pts)
        sxx = sum((p.x - c.x) ** 2 for p in pts); syy = sum((p.y - c.y) ** 2 for p in pts); sxy = sum((p.x - c.x) * (p.y - c.y) for p in pts)
        ang = 0.5 * math.atan2(2 * sxy, sxx - syy); u = Vector((math.cos(ang), math.sin(ang))); w = perp(u)
        ws = [(p - c).dot(w) for p in pts]; lo_w, hi_w = min(ws) + RIB_INSET, max(ws) - RIB_INSET
        if hi_w < lo_w: continue
        nr = max(1, int((hi_w - lo_w) / RIB_PASO) + 1)
        for k in range(nr):
            off = (lo_w + hi_w) / 2 if nr == 1 else lo_w + (hi_w - lo_w) * k / (nr - 1)
            P0 = c + w * off
            # cuerda dentro del tramo, recortada RIB_INSET de los bordes (los bordes del poligono de la region)
            ts = []
            for i in range(len(pts)):
                p, q = pts[i], pts[(i + 1) % len(pts)]; e = q - p; den = cross2(u, e)
                if abs(den) < 1e-9: continue
                t = cross2(p - P0, e) / den; v = cross2(p - P0, u) / den
                if 0 <= v <= 1: ts.append(t)
            if len(ts) < 2: continue
            ta, tb = min(ts) + RIB_INSET, max(ts) - RIB_INSET
            # partes libres por debajo (muestras cada 5 mm)
            libres = []; cur = None; t = ta
            while t <= tb + 1e-6:
                X = P0 + u * t
                okk = inside2(X, rg) and poly_dist(X, rg) >= RIB_INSET - 1 and all(bajo(Vector((Y.x, Y.y, zbot(tr, g, Y) - 0.1)), own) >= RIB_H + LUZ
                                                                                 for Y in (X - w * (RIB_W / 2 + 1), X, X + w * (RIB_W / 2 + 1)))
                if okk:
                    if cur is None: cur = [t, t]
                    cur[1] = t
                elif cur: libres.append(cur); cur = None
                t += 2.0
            if cur: libres.append(cur)
            for t0, t1 in libres:
                L = t1 - t0
                if L < 40: continue
                kk = max(1, math.ceil(L / CAP_MAX))
                for j in range(kk):
                    a0, a1 = t0 + L * j / kk, t0 + L * (j + 1) / kk - (2.0 if j < kk - 1 else 0.0)
                    A_, B_ = P0 + u * a0, P0 + u * a1
                    quad = [A_ - w * (RIB_W / 2), B_ - w * (RIB_W / 2), B_ + w * (RIB_W / 2), A_ + w * (RIB_W / 2)]
                    zt_ = [zbot(tr, g, q) for q in quad]; zl_ = [z - RIB_H / max(nrm.z, 0.3) for z in zt_]
                    bm = bmesh.new(); prism(bm, quad, zl_, zt_)
                    ob = to_obj(f"PETG_Nervio_{tr.name}_{len([p for p in PIEZAS if p['tray'] == tr.name and p['tipo'] == 'nervio']) + 1}", bm, coll, matR)
                    PIEZAS.append(dict(nombre=ob.name, tipo="nervio", obj=ob, tray=tr.name, info=f"{a1 - a0:.0f} x {RIB_W:g} x {RIB_H:g} mm"))

# ------------------------------------------------------------------ choques: piezas que chocan se quitan
def bvh_mm(o, shrink=0.0, ya_mm=False):
    oe = o.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = oe.to_mesh(); b = bmesh.new(); b.from_mesh(me); oe.to_mesh_clear()
    b.transform(o.matrix_world if ya_mm else Matrix.Scale(1000.0, 4) @ o.matrix_world)
    if shrink:
        b.normal_update()
        for v in b.verts: v.co -= v.normal * shrink
    t = BVHTree.FromBMesh(b); b.free(); return t
otros = [o for o in bpy.context.view_layer.objects if o.type == 'MESH' and o.visible_get() and o.users_collection
         and coll not in o.users_collection and not o.name.startswith(("Huevo", "tmp", "PETG_Escuadras"))
         and not (o.name.startswith("Bandeja") and o.hide_get())]
OBV = {o.name: bvh_mm(o, 0.1) for o in otros}
def comun_mm3(a, b, N=6000):
    """volumen comun real (mm3) por muestreo de puntos: dentro de ambos segun paridad de rayos"""
    import random
    ta = bvh_mm(a, 0.0, coll in a.users_collection); tb = bvh_mm(b, 0.0, coll in b.users_collection)
    def caja(o, ya):
        m_ = o.matrix_world if ya else Matrix.Scale(1000.0, 4) @ o.matrix_world
        ws = [m_ @ Vector(v.co) for v in o.data.vertices]
        return [min(w[k] for w in ws) for k in range(3)], [max(w[k] for w in ws) for k in range(3)]
    (a0, a1), (b0, b1) = caja(a, coll in a.users_collection), caja(b, coll in b.users_collection)
    lo = [max(a0[k], b0[k]) for k in range(3)]; hi = [min(a1[k], b1[k]) for k in range(3)]
    if any(lo[k] >= hi[k] for k in range(3)): return 0.0
    def dentro(t, P):
        n = 0
        for d in (Vector((0.3, 0.5, 0.81)).normalized(), Vector((-0.7, 0.2, -0.68)).normalized(), Vector((0.1, -0.95, 0.29)).normalized()):
            c = 0; q_ = P.copy()
            for _ in range(80):
                h = t.ray_cast(q_, d, 1e4)
                if h[0] is None: break
                c += 1; q_ = h[0] + d * 1e-4
            n += c % 2
        return n >= 2
    rnd = random.Random(7); k = 0
    for _ in range(N):
        P = Vector([rnd.uniform(lo[i], hi[i]) for i in range(3)])
        if dentro(ta, P) and dentro(tb, P): k += 1
    return (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2]) * k / N
quitadas = []
_orden = {"esquinero": 0, "nervio": 1, "borde": 2, "zocalo": 3}   # ante un choque se quita primero el esquinero suelto, luego el nervio
for p in sorted(PIEZAS, key=lambda p: _orden[p["tipo"]]):
    t = bvh_mm(p["obj"], 0.15, True)
    hit = next((nm for nm, bv in OBV.items() if t.overlap(bv)), None)
    if hit is None:
        hit = next((q["nombre"] for q in PIEZAS if q is not p and q["obj"].name in bpy.data.objects and t.overlap(bvh_mm(q["obj"], 0.15, True))), None)
    if hit and hit in [q_["nombre"] for q_ in PIEZAS] and comun_mm3(p["obj"], bpy.data.objects[hit]) < 1.0:
        hit = None          # dos refuerzos que solo se tocan (media madera): falso positivo del encogido
    if hit:
        bv2 = OBV.get(hit) or bvh_mm(bpy.data.objects[hit], 0.15, True)
        prs = t.overlap(bv2); me_ = p["obj"].data
        cs = [me_.polygons[i].center for i, j in prs[:200]] if prs else []
        donde = (" en x%.0f y%.0f z%.0f" % tuple(sum(cs, Vector()) / len(cs))) if cs else ""
        quitadas.append(f"{p['nombre']} ({p['tipo']}, {p['info']}) choca con {hit}{donde}")
        for cid in ZOC_CLIPS.get(p["nombre"], []): CUBIERTAS.discard(cid)      # esas escuadras siguen haciendo falta
        bpy.data.objects.remove(p["obj"], do_unlink=True); PIEZAS.remove(p)

# ------------------------------------------------------------------ escala a metros (escena), STL y lista
for p in PIEZAS:
    p["obj"].data.transform(Matrix.Scale(0.001, 4))
# reparacion final: un solo cuerpo cerrado por pieza (funde esquineros, cierra cunas y medias maderas)
_rep_ns = {"__name__": "reparar_zocalos"}
exec(open(os.path.join(BASE, "scripts", "reparar_zocalos_ovum2_2.py"), encoding="utf-8").read(), _rep_ns)
REPARADAS = _rep_ns["reparar_todos"]([p["obj"] for p in PIEZAS if p["tipo"] == "zocalo"], guardar_viejo=False)
for nm_, inf in REPARADAS.items():
    if not inf.get("aplicado"): av(f"{nm_}: no se pudo dejar en un solo cuerpo cerrado ({inf.get('despues_cuerpos_nm')})")
for f_ in os.listdir(REF_OUT):
    if f_.endswith(".stl"): os.remove(os.path.join(REF_OUT, f_))
for p in PIEZAS:
    o = p["obj"]; bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.wm.stl_export(filepath=os.path.join(REF_OUT, o.name.replace("PETG_", "") + ".stl"), export_selected_objects=True, global_scale=1000.0)
from collections import Counter
cnt = Counter((p["tray"], p["tipo"]) for p in PIEZAS)
ins = 0
with open(os.path.join(REF_OUT, "Refuerzos_bandejas_lista.txt"), "w", encoding="utf-8") as fh:
    W = fh.write
    W("REFUERZOS IMPRESOS (PETG) PARA LAS BANDEJAS DE PVC 2 mm\n\n")
    W("Esquinero: poste en L/V por fuera de la esquina, de toda la altura de la pared. Insertos de laton M3 (D4.0)\n"
      "  colocados con soldador desde afuera; tornillo M3 cabeza redonda desde adentro de la bandeja: taladrar el PVC\n"
      "  D3.4 usando el esquinero como guia. Ademas, cianoacrilato o epoxi en el contacto.\n")
    W(f"Perfil de borde: angulo en L ({CAP_T} mm) que tapa el canto superior de la pared y baja {CAP_LEG:.0f} mm por fuera.\n"
      "  Pegado con cianoacrilato/epoxi. En paredes compartidas (huevos a ambos lados) solo tapa el canto.\n")
    W(f"Nervio: barra {RIB_W:g} x {RIB_H:g} mm pegada bajo el piso, para que no se combe.\n\n")
    W("Impresion: PETG, 4 perimetros, 40% relleno. Esquineros de pie; perfiles apoyados sobre el ala superior;\n"
      "  nervios acostados sobre la cara de 8 mm.\n\n")
    for tn in TR:
        ps = [p for p in PIEZAS if p["tray"] == tn]
        if not ps: continue
        W(f"{tn}: {cnt[(tn, 'esquinero')]} esquineros, {cnt[(tn, 'borde')]} perfiles de borde, {cnt[(tn, 'nervio')]} nervios\n")
        for p in ps:
            W(f"   {p['nombre'].replace('PETG_', ''):<34} {p['info']}\n")
            import re as _re
            m_ = _re.search(r"(\d+) insertos M3", p["info"])
            if m_: ins += int(m_.group(1))
    resto = Counter(round(c["ang"]) for c in CLIPS if id(c) not in CUBIERTAS)
    W(f"\nZocalo: angulo en L de {CT:g} mm, ala de {HH:.0f} mm bajo el piso y de {HV:.0f} mm por fuera, a lo largo de todo el borde inferior\n"
      "  de la pared; dobla las esquinas y lleva el esquinero incorporado. Las piezas se unen a media madera: el\n"
      "  tornillo M3 de la union atraviesa las dos. Reemplaza a las escuadras sueltas en esos tramos.\n")
    W("Escuadras sueltas que siguen haciendo falta (donde no entra el zocalo): " +
      (", ".join(f"{n} de {a} grados" for a, n in sorted(resto.items())) if resto else "ninguna") + "\n")
    W(f"\nInsertos de laton M3 (largo 4 mm, D ext ~4.5): {ins}   Tornillos M3 x 8 cabeza redonda: {ins}\n")
    if quitadas: W("\nNo se colocaron (chocaban con algo):\n" + "".join(f"   {q}\n" for q in quitadas))
    if AV: W("\nAvisos:\n" + "".join(f"   {a}\n" for a in AV))
res = dict(piezas={f"{k[0]}/{k[1]}": v for k, v in cnt.items()}, total=len(PIEZAS), insertos=ins, quitadas=quitadas, avisos=AV + rep["avisos"][:0], stl=REF_OUT)
if "blend" in ARGS:
    bpy.ops.wm.save_as_mainfile(filepath=ARGS[ARGS.index("blend") + 1], copy=True); res["blend"] = ARGS[ARGS.index("blend") + 1]
print("REFUERZOS " + json.dumps(res))
