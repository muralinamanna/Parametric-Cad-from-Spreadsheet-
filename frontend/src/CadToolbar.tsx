import {useState} from 'react'
import type {ReactNode, RefObject} from 'react'
import {Boxes, Eye, EyeOff, Grid3X3, Hand, House, Move3D, RotateCcw, RotateCw, Scan, Triangle, ZoomIn, ZoomOut} from 'lucide-react'
import {projectedViews} from './projectedViews'

type View = typeof projectedViews[number]
export type CadControls = {
  view:(view:View)=>void
  zoom:(factor:number)=>void
  rotate:(radians:number)=>void
  fit:()=>void
  show:(visible:boolean)=>void
  wireframe:(enabled:boolean)=>void
  grid:(enabled:boolean)=>void
  axes:(enabled:boolean)=>void
  pan:(enabled:boolean)=>void
}

function ViewIcon({name}:{name:View['name']}) {
  const faces = [
    {near:'Top', far:'Bottom', path:'M3 7l9-4 9 4-9 4z'},
    {near:'Front', far:'Rear', path:'M3 7l9 4v10l-9-4z'},
    {near:'Right', far:'Left', path:'M12 11l9-4v10l-9 4z'},
  ]
  return <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
    {faces.map(face=>{
      const near=face.near===name, far=face.far===name
      return <path key={face.near} d={face.path} stroke="currentColor" strokeWidth="1.35" strokeLinejoin="round"
        fill={near?'currentColor':far||name==='Isometric'?'#b9d5f3':'none'}
        strokeDasharray={far?'2 2':undefined}/>
    })}
  </svg>
}

function Tool({label,icon,disabled,pressed,onClick,tooltip}:{
  label:string,icon:ReactNode,disabled?:boolean,pressed?:boolean,onClick?:()=>void,tooltip?:string,
}) {
  return <span className="cad-tool" title={tooltip||label}>
    <button type="button" aria-label={label} aria-pressed={pressed} disabled={disabled} onClick={onClick}>
      {icon}
    </button>
  </span>
}

export default function CadToolbar({ready,controls}:{ready:boolean,controls:RefObject<CadControls|null>}) {
  const [hidden,setHidden]=useState(false)
  const [wireframe,setWireframe]=useState(false)
  const [grid,setGrid]=useState(false)
  const [axes,setAxes]=useState(false)
  const [pan,setPan]=useState(false)

  function reset(){
    const cad=controls.current
    if(!cad) return
    cad.view(projectedViews[6])
    cad.show(true)
    cad.wireframe(false)
    cad.grid(false)
    cad.axes(false)
    cad.pan(false)
    setHidden(false);setWireframe(false);setGrid(false);setAxes(false);setPan(false)
  }

  return <div className="cad-toolbar">
    <div role="group" aria-label="Standard CAD views">
      {projectedViews.map(view=><Tool key={view.name} label={view.name} tooltip={view.name+' view'}
        icon={<ViewIcon name={view.name}/>} disabled={!ready} onClick={()=>controls.current?.view(view)}/>)}
    </div>
    <div role="group" aria-label="CAD navigation">
      <Tool label="Zoom in" icon={<ZoomIn/>} disabled={!ready} onClick={()=>controls.current?.zoom(1.25)}/>
      <Tool label="Zoom out" icon={<ZoomOut/>} disabled={!ready} onClick={()=>controls.current?.zoom(0.8)}/>
      <Tool label="Rotate left" icon={<RotateCcw/>} disabled={!ready} onClick={()=>controls.current?.rotate(Math.PI/12)}/>
      <Tool label="Rotate right" icon={<RotateCw/>} disabled={!ready} onClick={()=>controls.current?.rotate(-Math.PI/12)}/>
      <Tool label="Fit to screen" icon={<Scan/>} disabled={!ready} onClick={()=>controls.current?.fit()}/>
      <Tool label="Pan mode" icon={<Hand/>} disabled={!ready} pressed={pan} onClick={()=>{controls.current?.pan(!pan);setPan(!pan)}}/>
      <Tool label="Reset view" icon={<House/>} disabled={!ready} onClick={reset}/>
    </div>
    <div role="group" aria-label="CAD display">
      <Tool label={hidden?'Show model':'Hide model'} icon={hidden?<EyeOff/>:<Eye/>} disabled={!ready}
        onClick={()=>{controls.current?.show(hidden);setHidden(!hidden)}}/>
      <Tool label="Wireframe" icon={<Triangle/>} disabled={!ready} pressed={wireframe}
        onClick={()=>{controls.current?.wireframe(!wireframe);setWireframe(!wireframe)}}/>
      <Tool label="XY grid" icon={<Grid3X3/>} disabled={!ready} pressed={grid}
        onClick={()=>{controls.current?.grid(!grid);setGrid(!grid)}}/>
      <Tool label="XYZ axes" icon={<Move3D/>} disabled={!ready} pressed={axes}
        onClick={()=>{controls.current?.axes(!axes);setAxes(!axes)}}/>
      <Tool label="Explode (requires a multi-part assembly)" icon={<Boxes/>} disabled/>
    </div>
  </div>
}
