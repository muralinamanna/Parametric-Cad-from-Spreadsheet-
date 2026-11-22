import {useEffect,useRef,useState} from 'react'
import * as THREE from 'three'
import {OrbitControls} from 'three/addons/controls/OrbitControls.js'
import type {Preview} from './model'

type Source={url:string,format:'glb'|'stl'}
type Props={preview:Preview,source?:never}|{preview?:never,source:Source}

function previewMesh(preview:Preview) {
  const p=preview.parameters
  const points=(x:number,y:number,w:number,h:number)=>[
    [x,y],[x+w,y],[x+w,y+h],[x,y+h],[x,y],
  ].map(([a,b])=>new THREE.Vector2(a,b))
  const outline=new THREE.Shape(points(0,0,p.boardWidth,p.boardHeight))
  outline.holes=preview.slots.map(([x,y])=>new THREE.Path(points(x,y,p.slotWidth,p.slotLength).reverse()))
  return makeMesh(new THREE.ExtrudeGeometry(outline,{depth:p.boardThickness,bevelEnabled:false}))
}

function makeMesh(geometry:THREE.BufferGeometry) {
  const mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:0x79a6d5,metalness:.16,roughness:.5,side:THREE.DoubleSide}))
  mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(geometry,25),
    new THREE.LineBasicMaterial({color:0x21384f,transparent:true,opacity:.6})))
  return mesh
}

async function loadMesh(source:Source,signal:AbortSignal) {
  const response=await fetch(source.url,{signal})
  if (!response.ok) throw new Error('The generated model could not be downloaded.')
  const bytes=await response.arrayBuffer()
  if (source.format==='glb'){
    const {GLTFLoader}=await import('three/addons/loaders/GLTFLoader.js')
    const {scene}=await new GLTFLoader().parseAsync(bytes,'')
    scene.rotation.x=Math.PI/2 // glTF is Y-up; the board datum is Z-up.
    return scene
  }
  const {STLLoader}=await import('three/addons/loaders/STLLoader.js')
  return makeMesh(new STLLoader().parse(bytes))
}

function disposeModel(model:THREE.Object3D) {
  model.traverse(object=>{
    if (!(object instanceof THREE.Mesh || object instanceof THREE.LineSegments)) return
    object.geometry.dispose()
    for (const material of Array.isArray(object.material)?object.material:[object.material]) material.dispose()
  })
}

export default function Scene({preview,source}:Props) {
  const mount=useRef<HTMLDivElement>(null)
  const [status,setStatus]=useState(source?'Loading generated model…':'')
  const url=source?.url, format=source?.format
  useEffect(()=>{
    const host=mount.current!
    const stopping=new AbortController()
    let teardown:()=>void=()=>{}
    async function start(){
      setStatus(url?'Loading generated model…':'')
      const model=preview?previewMesh(preview):await loadMesh({url:url!,format:format!},stopping.signal)
      if (stopping.signal.aborted){disposeModel(model);return}
      const bounds=new THREE.Box3().setFromObject(model)
      const size=bounds.getSize(new THREE.Vector3())
      const span=Math.max(size.x,size.y,size.z)
      if (!Number.isFinite(span)||span<=0){disposeModel(model);throw new Error('The generated model contains no viewable geometry.')}
      let renderer:THREE.WebGLRenderer
      try {renderer=new THREE.WebGLRenderer({antialias:true,alpha:true})}
      catch {disposeModel(model);throw new Error('WebGL is unavailable. You can still download the model.')}
      model.position.sub(bounds.getCenter(new THREE.Vector3()))
      const normalized=new THREE.Group()
      normalized.add(model)
      normalized.scale.setScalar(5/span)
      const scene=new THREE.Scene()
      scene.add(normalized,new THREE.HemisphereLight(0xffffff,0x576476,2.2))
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
        camera.zoom=Math.min(1,camera.aspect)
        camera.updateProjectionMatrix()
        renderer.setSize(host.clientWidth,host.clientHeight)
      })
      observer.observe(host)
      renderer.setAnimationLoop(()=>{controls.update();renderer.render(scene,camera)})
      teardown=()=>{
        observer.disconnect();renderer.setAnimationLoop(null);controls.dispose()
        disposeModel(model);renderer.dispose();renderer.domElement.remove()
      }
      setStatus('')
    }
    void start().catch(error=>{
      if (!stopping.signal.aborted) setStatus(error instanceof Error?error.message:'Unable to display the 3D model.')
    })
    return ()=>{stopping.abort();teardown()}
  },[preview,url,format])
  return <div className="scene" aria-label={source?'Generated CAD model viewer':'Interactive 3D pegboard preview'}>
    <div className="scene-mount" ref={mount}/>
    {status&&<p role="status">{status}</p>}
  </div>
}
