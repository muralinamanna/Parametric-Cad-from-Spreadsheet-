import {useEffect,useRef,useState} from 'react'
import type {PointerEvent,RefObject} from 'react'
import {Hand,Scan,ZoomIn,ZoomOut} from 'lucide-react'
import {projectedViews} from './projectedViews'

type Layers={gdt:boolean,tolerance:boolean}
const annotationSelector={gdt:'[data-annotation="gdt"]',tolerance:'[data-annotation="tolerance"]'}
const allLayers:Layers={gdt:true,tolerance:true}
const noLayers:Layers={gdt:false,tolerance:false}

function useDrawingLayers(url:string|undefined,shown:Layers) {
  const [drawing,setDrawing]=useState<{url:string,xml:Document,layers:Layers}>()
  const [filtered,setFiltered]=useState<{original:string,url:string}>()
  useEffect(()=>{
    if (!url) return
    const controller=new AbortController()
    fetch(url,{signal:controller.signal}).then(response=>{
      if (!response.ok) throw Error('Drawing unavailable')
      return response.text()
    }).then(text=>{
      if(controller.signal.aborted) return
      const xml=new DOMParser().parseFromString(text,'image/svg+xml')
      if(xml.documentElement.localName!=='svg') return
      setDrawing({url,xml,layers:{
        gdt:Boolean(xml.querySelector(annotationSelector.gdt)),
        tolerance:Boolean(xml.querySelector(annotationSelector.tolerance)),
      }})
    }).catch(()=>{})
    return ()=>controller.abort()
  },[url])
  const current=drawing?.url===url?drawing:undefined
  useEffect(()=>{
    if(!current||((shown.gdt||!current.layers.gdt)&&(shown.tolerance||!current.layers.tolerance))){
      setFiltered(undefined)
      return
    }
    const svg=current.xml.documentElement.cloneNode(true) as SVGElement
    for(const name of ['gdt','tolerance'] as const){
      if(!shown[name]) svg.querySelectorAll<SVGElement>(annotationSelector[name]).forEach(layer=>{
        layer.style.setProperty('display','none','important')
      })
    }
    const object=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml'}))
    setFiltered({original:current.url,url:object})
    return ()=>URL.revokeObjectURL(object)
  },[current,shown])
  return {src:filtered?.original===url&&filtered?filtered.url:url,layers:current?.layers||noLayers}
}

export default function DrawingReview({sheetUrl,tab,setTab,projections}:{
  sheetUrl?:string
  tab:'views'|'sheet'
  setTab:(tab:'views'|'sheet')=>void
  projections:RefObject<HTMLDivElement|null>
}) {
  const [zoom,setZoom]=useState(1)
  const [pan,setPan]=useState(false)
  const [shown,setShown]=useState<Layers>(allLayers)
  const viewport=useRef<HTMLDivElement>(null)
  const drag=useRef<{id:number,x:number,y:number,left:number,top:number}|null>(null)
  const {src,layers}=useDrawingLayers(sheetUrl,shown)
  const projected=tab==='views'
  const zoomTo=(value:number)=>setZoom(Math.min(4,Math.max(0.5,value)))
  const fit=()=>{setZoom(1);viewport.current?.scrollTo(0,0)}
  function switchView(mode:'views'|'sheet'){
    setTab(mode)
    fit()
  }
  function startDrag(event:PointerEvent<HTMLDivElement>){
    if (!pan||event.button!==0) return
    const target=event.currentTarget
    target.setPointerCapture(event.pointerId)
    drag.current={id:event.pointerId,x:event.clientX,y:event.clientY,left:target.scrollLeft,top:target.scrollTop}
  }
  function moveDrag(event:PointerEvent<HTMLDivElement>){
    const active=drag.current
    if(active?.id!==event.pointerId) return
    event.currentTarget.scrollTo(active.left+active.x-event.clientX,active.top+active.y-event.clientY)
  }
  function endDrag(event:PointerEvent<HTMLDivElement>){
    if(drag.current?.id===event.pointerId) drag.current=null
  }
  const noAnnotations=!layers.gdt&&!layers.tolerance

  return <>
    {sheetUrl&&<div className="segmented review-tabs" role="group" aria-label="Drawing preview mode">
      <button type="button" aria-pressed={projected} onClick={()=>switchView('views')}>Projected views</button>
      <button type="button" aria-pressed={!projected} onClick={()=>switchView('sheet')}>Drawing sheet</button>
    </div>}
    <div className="drawing-tools" role="group" aria-label="Drawing tools">
      <button type="button" aria-label="Zoom out drawing" title="Zoom out drawing" disabled={zoom<=0.5} onClick={()=>zoomTo(zoom/1.25)}><ZoomOut/></button>
      <output aria-label="Drawing zoom">{Math.round(zoom*100)}%</output>
      <button type="button" aria-label="Zoom in drawing" title="Zoom in drawing" disabled={zoom>=4} onClick={()=>zoomTo(zoom*1.25)}><ZoomIn/></button>
      <button type="button" aria-label="Drawing pan mode" title="Drag to pan drawing" aria-pressed={pan} onClick={()=>setPan(!pan)}><Hand/></button>
      <button type="button" aria-label="Fit drawing" title="Fit drawing to width" onClick={fit}><Scan/></button>
      {(['gdt','tolerance'] as const).map(name=>{
        const label=name==='gdt'?'GD&T':'Tolerances'
        return <button key={name} type="button" aria-label={label} aria-pressed={!projected&&layers[name]&&shown[name]}
          disabled={projected||!layers[name]} title={projected?'Available on annotated drawing sheets':layers[name]?'Show or hide '+label:'No '+label+' annotations in this sheet'}
          onClick={()=>setShown({...shown,[name]:!shown[name]})}>{label}</button>
      })}
    </div>
    {noAnnotations&&sheetUrl&&<p className="drawing-layer-note">This sheet has no separate GD&T or tolerance layers.</p>}
    <div ref={viewport} className={`drawing-viewport${pan?' drawing-pan':''}`} role="region" aria-label="Drawing viewport" tabIndex={0}
      onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag} onLostPointerCapture={endDrag}>
      <div className="drawing-scale" style={{width:`${zoom*100}%`}}>
        <div className="review-views review-paper" ref={projections} hidden={!projected}>
          {[0,6,1,2,3,4,5].map(i=>projectedViews[i]).map(({name})=><figure key={name}>
            <canvas data-view={name} role="img" aria-label={`${name} view of the CAD model`}/>
            <figcaption>{name}</figcaption>
          </figure>)}
        </div>
        {!projected&&src&&<img className="review-sheet" src={src} alt="Dimensioned drawing sheet for the CAD model" draggable={false}/>}
      </div>
    </div>
  </>
}
