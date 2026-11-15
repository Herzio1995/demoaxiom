"""
Ovum1_9: baja el travesano bajo las bandejas superiores para que el piso de alucobond de 5 mm de la
BandejaCentral apoye con 0.5 mm de holgura (como antes con la superficie sin espesor).
Bajan el travesano y la parte alta de lo que lo sostiene (poste central y cartelas PETG): todos los
vertices en la franja y del travesano que estan a la altura de su cara inferior o mas arriba.
Se aplica a la copia unida visible y a las piezas sueltas ocultas.
Uso:  blender --background Ovum1_9.blend --python bajar_travesano_bandeja_central_ovum1_9.py [-- save]
"""
import bpy, bmesh, json, sys

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
O = bpy.data.objects
T_ACM = 0.005; HOLG = 0.0005
J = O["Bastidor_Largueros_2020.003"]
rep = {}

# travesano(s): caras de aluminio anchas en x (>0.3 m) por encima de z 0.115. Hay dos cajas solapadas
# (y 307.5-332.5 suelta y 317.5-342.5 unida al poste central): se bajan juntas.
bm = bmesh.new(); bm.from_mesh(J.data); bm.transform(J.matrix_world)
ws = [f for f in bm.faces if max(v.co.x for v in f.verts) - min(v.co.x for v in f.verts) > 0.15 and min(v.co.z for v in f.verts) > 0.115]
assert ws, "no se encontro el travesano"
vv = {v for f in ws for v in f.verts}
tr = (min(v.co.x for v in vv), max(v.co.x for v in vv), min(v.co.y for v in vv), max(v.co.y for v in vv),
      min(v.co.z for v in vv), max(v.co.z for v in vv))
bm.free()
src = O["BandejaCentral"]
z_piso = min((src.matrix_world @ v.co).z for v in src.data.vertices)        # cara de los huevos, parte baja
D = tr[5] - (z_piso - T_ACM - HOLG)
rep["travesano_antes_mm"] = [round(tr[4] * 1000, 2), round(tr[5] * 1000, 2)]
rep["bajada_mm"] = round(D * 1000, 2)

def bajar(o):
    mw = o.matrix_world; mi = mw.inverted(); n = 0
    for v in o.data.vertices:
        w = mw @ v.co
        if tr[2] - 1e-4 <= w.y <= tr[3] + 1e-4 and w.z >= tr[4] - 1e-4 and tr[0] - 1e-4 <= w.x <= tr[1] + 1e-4:
            w.z -= D; v.co = mi @ w; n += 1
    o.data.update(); return n
rep["vertices"] = {"Bastidor_Largueros_2020.003": bajar(J)}
for nm in ("Travesano_Bandejas_Superiores_2020", "Cartelas_Travesano", "Poste_Central_Bandejas", "Bastidor_Largueros_2020.001"):
    if O.get(nm) and O[nm].type == 'MESH': rep["vertices"][nm] = bajar(O[nm])
# bandejas inferiores: bordes superiores de pared que pasan bajo el piso de la central quedan 0.5 mm debajo
Vb = [(src.matrix_world @ v.co) for v in src.data.vertices]
PROF = [Vb[i] for i in (27, 1, 0, 20, 12, 7)]
PLAN = [Vb[i] for i in (7, 12, 20, 0, 1, 22, 27, 28, 4, 3, 24, 13, 6)]
def z_floor(y):
    for a_, b_ in zip(PROF[:-1], PROF[1:]):
        if b_.y - 1e-6 <= y <= a_.y + 1e-6:
            t = (a_.y - y) / max(a_.y - b_.y, 1e-9); dz = b_.z - a_.z; L = (a_.y - b_.y)
            cosa = L / (L * L + dz * dz) ** 0.5
            return a_.z + t * dz - T_ACM / cosa
    return None
def inside(x, y):
    c = False; n = len(PLAN)
    for i in range(n):
        a_, b_ = PLAN[i], PLAN[(i + 1) % n]
        if (a_.y > y) != (b_.y > y) and x < (b_.x - a_.x) * (y - a_.y) / (b_.y - a_.y) + a_.x: c = not c
    return c
rep["bandejas_inferiores"] = {}
for nm in ("BandejaLDown", "BandejaRDown"):
    o = O.get(nm)
    if not o: continue
    mw = o.matrix_world; mi = mw.inverted(); W = {v.index: mw @ v.co for v in o.data.vertices}; low = {}
    for e in o.data.edges:
        a_, b_ = W[e.vertices[0]], W[e.vertices[1]]
        if min(a_.z, b_.z) < 0.12: continue
        need = 0.0
        for k in range(41):
            p = a_ + (b_ - a_) * (k / 40)
            if inside(p.x, p.y):
                zf = z_floor(p.y)
                if zf is not None: need = max(need, p.z - (zf - HOLG))
        if need > 0:
            for vi in e.vertices: low[vi] = max(low.get(vi, 0.0), need)
    for vi, d in low.items():
        w = W[vi].copy(); w.z -= d; o.data.vertices[vi].co = mi @ w
    o.data.update()
    rep["bandejas_inferiores"][nm] = {f"{W[vi].x*1000:.1f},{W[vi].y*1000:.1f},{W[vi].z*1000:.1f}": round(d * 1000, 2) for vi, d in low.items()}
rep["travesano_despues_mm"] = [round((tr[4] - D) * 1000, 2), round((tr[5] - D) * 1000, 2)]
rep["y_mm"] = [round(tr[2] * 1000, 2), round(tr[3] * 1000, 2)]
if "save" in argv:
    bpy.ops.wm.save_mainfile(); rep["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(rep))
