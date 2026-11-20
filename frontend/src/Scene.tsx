import {useEffect,useRef,useState} from 'react'
import * as THREE from 'three'
import {OrbitControls} from 'three/addons/controls/OrbitControls.js'
import type {Preview} from './model'

export default function Scene({preview}:{preview:Preview}) {
  const mount=useRef<HTMLDivElement>(null)
  const [error,setError]=useState(false)
  useEffect(()=>{
    const host=mount.current!
    let renderer:THREE.WebGLRenderer
    try { renderer=new THREE.WebGLRenderer({antialias:true,alpha:true}) }
    catch { setError(true);return }
    const p=preview.parameters
    const factor=5/Math.max(p.boardHeight,p.boardWidth,p.boardThickness)
    const points = (x:number,y:number,w:number,h:number) => [[x,y],[x+w,y],[x+w,y+h],[x,y+h],[x,y]].map(([a,b])=>new THREE.Vector2(a*factor,b*factor))
    const outline=new THREE.Shape(points(0,0,p.boardWidth,p.boardHeight))
    outline.holes=preview.slots.map(([x,y])=>new THREE.Path(points(x,y,p.slotWidth,p.slotLength).reverse()))
    const geometry=new THREE.ExtrudeGeometry(outline,{depth:p.boardThickness*factor,bevelEnabled:false})
    geometry.center()
    const material=new THREE.MeshStandardMaterial({color:0x79a6d5,metalness:.16,roughness:.5,side:THREE.DoubleSide})
    const mesh=new THREE.Mesh(geometry,material)
    const edges=new THREE.EdgesGeometry(geometry,25)
    const lineMaterial=new THREE.LineBasicMaterial({color:0x21384f,transparent:true,opacity:.6})
    mesh.add(new THREE.LineSegments(edges,lineMaterial))
    const scene=new THREE.Scene()
    scene.add(mesh,new THREE.HemisphereLight(0xffffff,0x576476,2.2))
    const light=new THREE.DirectionalLight(0xffffff,2)
    light.position.set(-4,-5,6)
    scene.add(light)
    const camera=new THREE.PerspectiveCamera(42,1,.1,100)
    camera.up.set(0,0,1)
    camera.position.set(4,-5,7)
    renderer.setPixelRatio(Math.min(devicePixelRatio,2))
    host.appendChild(renderer.domElement)
    const controls=new OrbitControls(camera,renderer.domElement)
    controls.enableDamping=true
    const observer=new ResizeObserver(()=>{
      camera.aspect=host.clientWidth/Math.max(host.clientHeight,1)
      camera.updateProjectionMatrix()
      renderer.setSize(host.clientWidth,host.clientHeight)
    })
    observer.observe(host)
    renderer.setAnimationLoop(()=>{ controls.update();renderer.render(scene,camera) })
    return ()=>{observer.disconnect();renderer.setAnimationLoop(null);controls.dispose();edges.dispose();lineMaterial.dispose();material.dispose();geometry.dispose();renderer.dispose();renderer.domElement.remove()}
  },[preview])
  return <div ref={mount} className="scene" aria-label="Interactive 3D pegboard preview">{error&&<p>WebGL is unavailable. Switch to 2D Top.</p>}</div>
}
