"""
Ovum2_2: repara los zocalos PETG de las bandejas (PETG_Zocalo_*) sin cambiar su forma.
  - funde los cuerpos encimados (esquinero pegado a la L) en uno solo
  - rellena las cunas finas (< 2 mm) donde dos partes se tocaban solo por una arista
  - une con un puente de 0.1 mm las partes que solo se apoyaban cara con cara (lengueta de la media madera)
  - solo aplica el resultado si queda 1 cuerpo cerrado y el volumen es coherente; si no, deja la pieza como estaba
  (la malla anterior queda guardada como <nombre>_viejo)
Uso:  blender --background <archivo>.blend --python reparar_zocalos_ovum2_2.py -- [save]
      o desde otro script: exec(...) y llamar reparar_todos()
"""
import bpy, bmesh, json, sys
O=bpy.data.objects; sc=bpy.context.scene
NOMBRES=None
SOLVER='MANIFOLD'   # None = todos los PETG_Zocalo_* con mas de un cuerpo o aristas abiertas
def stats(b):
    seen=set(); isl=0
    for f in b.faces:
        if f in seen: continue
        isl+=1; st=[f]; seen.add(f)
        while st:
            g=st.pop()
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen: seen.add(h); st.append(h)
    return isl, sum(1 for e in b.edges if not e.is_manifold)
def capas(b):
    """separa en cascarones cerrados: corta por aristas con >2 caras y agrupa por conectividad"""
    bmesh.ops.split_edges(b, edges=[e for e in b.edges if len(e.link_faces)>2])
    seen=set(); out=[]
    for f in b.faces:
        if f in seen: continue
        st=[f]; comp=[]; seen.add(f)
        while st:
            g=st.pop(); comp.append(g)
            for e in g.edges:
                if len(e.link_faces)!=2: continue
                for h in e.link_faces:
                    if h not in seen: seen.add(h); st.append(h)
        out.append(comp)
    return out
def reparar(o):
    b=bmesh.new(); b.from_mesh(o.data)
    bmesh.ops.remove_doubles(b,verts=b.verts,dist=1e-5); bmesh.ops.dissolve_degenerate(b,edges=b.edges,dist=1e-6)
    bmesh.ops.delete(b,geom=[v for v in b.verts if not v.link_faces],context='VERTS')
    antes=stats(b); vol0=b.calc_volume()
    objs=[]
    # relleno de cunas calculado sobre la malla original (aristas con 4 caras: dos partes que se tocan por una linea)
    b.normal_update(); rell=bmesh.new(); hechas=set()
    for e in [e for e in b.edges if len(e.link_faces)==4]:
        fs=list(e.link_faces); par=None
        for i in range(4):
            for j in range(i+1,4):
                if fs[i].normal.dot(fs[j].normal) < -0.9: par=(fs[i],fs[j])
        if not par: continue
        fB,fA=sorted(par,key=lambda f:f.calc_area())
        if fB.index in hechas: continue
        hechas.add(fB.index)
        n=fB.normal; pa=fA.calc_center_median(); na=fA.normal; pts=[]; ts=[]
        for v in fB.verts:
            den=n.dot(na)
            if abs(den)<1e-6: continue
            t=(pa-v.co).dot(na)/den; ts.append(t); pts+=[v.co-n*0.00005, v.co+n*(t+0.00005)]
        if len(pts)<6 or max(abs(x) for x in ts)>0.002 or min(ts)<-0.0002: continue
        vs=[rell.verts.new(p_) for p_ in pts]; bmesh.ops.convex_hull(rell,input=vs)
        sueltos=[v for v in vs if v.is_valid and not v.link_faces]
        if sueltos: bmesh.ops.delete(rell,geom=sueltos,context='VERTS')
    if rell.faces and SOLVER=='MANIFOLD':
        bmesh.ops.recalc_face_normals(rell,faces=rell.faces)
        me_r=bpy.data.meshes.new("_c"); rell.to_mesh(me_r)
        ob_r=bpy.data.objects.new("_c",me_r); sc.collection.objects.link(ob_r); ob_r.matrix_world=o.matrix_world.copy()
        objs.append((0.0,ob_r))
    rell.free()
    for comp in capas(b):
        pb=bmesh.new(); vm={}
        for f in comp:
            for v in f.verts:
                if v not in vm: vm[v]=pb.verts.new(v.co)
            try: pb.faces.new([vm[v] for v in f.verts])
            except ValueError: pass
        borde=[e for e in pb.edges if e.is_boundary]
        if borde:
            r_=bmesh.ops.holes_fill(pb,edges=borde,sides=0); bmesh.ops.triangulate(pb,faces=r_["faces"])
        bmesh.ops.recalc_face_normals(pb,faces=pb.faces)
        v=abs(pb.calc_volume())
        if v<1e-12: pb.free(); continue            # astillas sin volumen
        me=bpy.data.meshes.new("_c"); pb.to_mesh(me); pb.free()
        ob=bpy.data.objects.new("_c",me); sc.collection.objects.link(ob); ob.matrix_world=o.matrix_world.copy(); objs.append((v,ob))
    b.free()
    objs.sort(key=lambda x:-x[0])
    base=objs[0][1]
    for v,ob in objs[1:]:
        md=base.modifiers.new("u",'BOOLEAN'); md.operation='UNION'; md.object=ob; md.solver=SOLVER
        if SOLVER=='EXACT': md.use_self=True
        dg=bpy.context.evaluated_depsgraph_get(); dg.update()
        me2=bpy.data.meshes.new_from_object(base.evaluated_get(dg)); base.modifiers.remove(md)
        old=base.data; base.data=me2; bpy.data.meshes.remove(old)
    # cunas: dos partes que se tocan solo por una arista (4 caras). Se rellena proyectando la cara chica sobre la
    # opuesta (con 0.05 mm de solape) y uniendo.
    for _it in range(3 if SOLVER=='EXACT' else 0):
        bb=bmesh.new(); bb.from_mesh(base.data); bb.normal_update()
        malas=[e for e in bb.edges if len(e.link_faces)==4]
        if not malas: bb.free(); break
        rell=bmesh.new(); hechas=set()
        for e in malas:
            fs=list(e.link_faces); par=None
            for i in range(4):
                for j in range(i+1,4):
                    if fs[i].normal.dot(fs[j].normal) < -0.9: par=(fs[i],fs[j])
            if not par: continue
            fB,fA=sorted(par,key=lambda f:f.calc_area())
            if fB.index in hechas: continue
            hechas.add(fB.index)
            n=fB.normal; pa=fA.calc_center_median(); na=fA.normal
            pts=[]; ts=[]
            for v in fB.verts:
                den=n.dot(na)
                if abs(den)<1e-6: continue
                t=(pa-v.co).dot(na)/den; ts.append(t)
                q=v.co+n*(t+0.00005)
                pts+= [v.co-n*0.00005, q]
            if len(pts)<6 or not ts or max(abs(x) for x in ts) > 0.002 or min(ts) < -0.0002: continue   # solo cunas finas (< 2 mm)
            vs=[rell.verts.new(p_) for p_ in pts]
            r_=bmesh.ops.convex_hull(rell,input=vs)
            sueltos=[v for v in vs if v.is_valid and not v.link_faces]
            if sueltos: bmesh.ops.delete(rell,geom=sueltos,context='VERTS')
        bb.free()
        if not rell.faces: rell.free(); break
        bmesh.ops.recalc_face_normals(rell,faces=rell.faces)
        me_r=bpy.data.meshes.new("_rell"); rell.to_mesh(me_r); rell.free()
        orr=bpy.data.objects.new("_rell",me_r); sc.collection.objects.link(orr); orr.matrix_world=base.matrix_world.copy()
        md=base.modifiers.new("u",'BOOLEAN'); md.operation='UNION'; md.object=orr; md.solver='EXACT'; md.use_self=True
        dg=bpy.context.evaluated_depsgraph_get(); dg.update()
        me2=bpy.data.meshes.new_from_object(base.evaluated_get(dg)); base.modifiers.remove(md)
        old=base.data; base.data=me2; bpy.data.meshes.remove(old); O.remove(orr); bpy.data.meshes.remove(me_r)
    r=bmesh.new(); r.from_mesh(base.data)
    if SOLVER=='EXACT':
        bmesh.ops.remove_doubles(r,verts=r.verts,dist=1e-6); bmesh.ops.dissolve_degenerate(r,edges=r.edges,dist=1e-6)
    bmesh.ops.recalc_face_normals(r,faces=r.faces)
    # puentes: cuerpos que solo se apoyan cara con cara (lengueta de la media madera, tramos del inglete). Se
    # extruye 0.1 mm la cara de contacto hacia el cuerpo vecino y se une (Manifold).
    from mathutils.bvhtree import BVHTree
    for _it in range(3):
        seen=set(); comps=[]
        for f in r.faces:
            if f in seen: continue
            st=[f]; comp=[]; seen.add(f)
            while st:
                g=st.pop(); comp.append(g)
                for e in g.edges:
                    for h in e.link_faces:
                        if h not in seen: seen.add(h); st.append(h)
            comps.append(comp)
        if len(comps)<2: break
        comps.sort(key=lambda c:-len(c))
        pr=bmesh.new(); hay=False
        for i,cB in enumerate(comps[1:],1):
            otros_=[f for j,c in enumerate(comps) if j!=i for f in c]
            tb=bmesh.new(); vm={}
            for f in otros_:
                for v in f.verts:
                    if v not in vm: vm[v]=tb.verts.new(v.co)
                try: tb.faces.new([vm[v] for v in f.verts])
                except ValueError: pass
            bmesh.ops.triangulate(tb,faces=tb.faces); tree=BVHTree.FromBMesh(tb); tb.free()
            for f in cB:
                c=f.calc_center_median(); h=tree.find_nearest(c, 2e-6)
                if h[0] is None or h[1].dot(f.normal) > -0.99: continue
                n=f.normal; lo=[pr.verts.new(v.co - n*0.00001) for v in f.verts]; hi=[pr.verts.new(v.co + n*0.0001) for v in f.verts]
                k=len(lo)
                pr.faces.new(list(reversed(lo))); pr.faces.new(hi)
                for q in range(k): pr.faces.new((lo[q],lo[(q+1)%k],hi[(q+1)%k],hi[q]))
                hay=True
        if not hay: pr.free(); break
        bmesh.ops.recalc_face_normals(pr,faces=pr.faces)
        me_p=bpy.data.meshes.new("_pu"); pr.to_mesh(me_p); pr.free()
        op_=bpy.data.objects.new("_pu",me_p); sc.collection.objects.link(op_); op_.matrix_world=base.matrix_world.copy()
        r.to_mesh(base.data); base.data.update()
        md=base.modifiers.new("u",'BOOLEAN'); md.operation='UNION'; md.object=op_; md.solver='MANIFOLD'
        dg=bpy.context.evaluated_depsgraph_get(); dg.update()
        me2=bpy.data.meshes.new_from_object(base.evaluated_get(dg)); base.modifiers.remove(md)
        old=base.data; base.data=me2; bpy.data.meshes.remove(old); O.remove(op_); bpy.data.meshes.remove(me_p)
        r.free(); r=bmesh.new(); r.from_mesh(base.data)
    # cuerpos del resultado: se quitan astillas (< 0.5 mm3)
    seen=set(); comps=[]
    for f in r.faces:
        if f in seen: continue
        st=[f]; comp=[]; seen.add(f)
        while st:
            g=st.pop(); comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen: seen.add(h); st.append(h)
        comps.append((abs(sum(g.calc_area()*g.normal.dot(g.calc_center_median()) for g in comp)/3), comp))
    astillas=[c for v,c in comps if v<0.5e-9]
    for c in astillas: bmesh.ops.delete(r,geom=c,context='FACES')
    bmesh.ops.delete(r,geom=[v for v in r.verts if not v.link_faces],context='VERTS')
    cuerpos_vol=sorted([round(v*1e9,1) for v,c in comps if v>=0.5e-9],reverse=True)
    despues=stats(r); vol1=r.calc_volume()
    vols=[v for v,_ in objs]
    info={"cuerpos_mm3":cuerpos_vol,"antes_cuerpos_nm":antes,"capas":len(objs),"despues_cuerpos_nm":despues,"vol_cm3":round(vol1*1e6,3),
          "vol_capa_mayor":round(max(vols)*1e6,3),"vol_suma_capas":round(sum(vols)*1e6,3)}
    ok = despues==(1,0) and max(vols)-0.05e-6 <= vol1 <= sum(vols)+0.4e-6   # rellenos de cunas suman algo
    if ok:
        me=bpy.data.meshes.new(o.data.name); r.to_mesh(me)
        for m_ in o.data.materials: me.materials.append(m_)
        me.polygons.foreach_set("use_smooth",[False]*len(me.polygons))
        viejo=o.data; o.data=me
        if GUARDAR_VIEJO: viejo.name=o.name+"_viejo"; viejo.use_fake_user=True
        elif viejo.users==0: bpy.data.meshes.remove(viejo)
    r.free()
    for _,ob in objs:
        if ob.name in O: me_=ob.data; O.remove(ob); bpy.data.meshes.remove(me_)
    info["aplicado"]=ok
    return info
GUARDAR_VIEJO=True
def reparar_todos(objs=None, guardar_viejo=True):
  global GUARDAR_VIEJO
  GUARDAR_VIEJO=guardar_viejo
  res={}
  cand = objs if objs is not None else [x for x in O if x.name.startswith("PETG_Zocalo_") and x.type=='MESH' and not x.name.endswith("_viejo")]
  for o in sorted(cand,key=lambda x:x.name):
    b=bmesh.new(); b.from_mesh(o.data); st=stats(b); b.free()
    if (NOMBRES is None and st!=(1,0)) or (NOMBRES and o.name in NOMBRES):
        res[o.name]=reparar(o)
  return res
if __name__ == "__main__":
    for k,v in reparar_todos().items(): print('REP',k.replace('PETG_Zocalo_',''),v)
    if "--" in sys.argv and "save" in sys.argv[sys.argv.index("--"):]: bpy.ops.wm.save_mainfile(); print("GUARDADO")
