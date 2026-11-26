import {lazy, Suspense, useEffect,useRef,useState} from 'react'
import {createRoot} from 'react-dom/client'
import {Activity, ArrowDownToLine, ArrowRight, Box, Check, ChevronDown, CircleHelp, Eye, ClipboardCheck, FileSpreadsheet, FileText, Grid2X2, Layers3, LoaderCircle, Maximize2, Play, RotateCcw, ScanLine, Upload, X} from 'lucide-react'
import {calculate, defaults, fields, number} from './model'
import type {Input, Key, Parameters, Preview} from './model'
import DrawingReview from './DrawingReview'
import ProductDetails from './ProductDetails'
import {api} from './api'
import DetailedDesign from './DetailedDesign'
import type {DesignSource} from './DetailedDesign'
import './styles.css'
import captions from './captions.vtt?raw'

const nominalPreview=calculate(defaults)
const Scene=lazy(()=>import('./Scene'))
const setupGuide='https://github.com/muralinamanna/Parametric-Cad-from-Spreadsheet-/blob/b5bf3d5835ce7a0e45a3d6edbcf1df2c14730064/README.md'
const fullAppSetup=setupGuide+'#run-the-full-local-app'
const embeddedSamples=document.getElementById('embedded-samples')?.textContent
const bundledSamples:Record<string,[string,string]>=embeddedSamples?JSON.parse(embeddedSamples):{}
const localSampleUrls=new Map<string,string>()
function sampleUrl(name:string) {
  const bundled=bundledSamples[name]
  if (!bundled) return './samples/'+name
  const cached=localSampleUrls.get(name)
  if (cached) return cached
  const [type,base64]=bundled
  const bytes=Uint8Array.from(atob(base64),byte=>byte.charCodeAt(0))
  const url=URL.createObjectURL(new Blob([bytes],{type}))
  localSampleUrls.set(name,url)
  return url
}
const captionUrl='data:text/vtt;charset=utf-8,'+encodeURIComponent(captions)
const resultFiles=['pegboard.FCStd','pegboard.sc','pegboard.step','pegboard.dxf','pegboard.svg','pegboard.png','pegboard.pdf']
const modelFiles=[...resultFiles,'pegboard.glb','pegboard.stl']
const formatNames=['FCStd','SolidCraft SC','STEP','DXF','SVG','PNG','PDF']
const cases=[['Minimum',30,49],['Nominal',300,200],['Wider',360,200]] as const
const downloadable:Record<string,string>={
  ...Object.fromEntries(resultFiles.filter(name=>!name.endsWith(".sc")).map(name=>[name,sampleUrl(name)])),
  'pegboard_test_log.csv':sampleUrl('pegboard_test_log.csv'),'validation_report.json':sampleUrl('validation_report.json'),
  ...Object.fromEntries([1,2,3].map(i=>[`case_${i}.FCStd`,sampleUrl(`case_${i}.FCStd`)]))
}
type Engine='freecad'|'solidcraft'
type EngineMode='auto'|Engine
const engineNames:Record<Engine,string>={freecad:'FreeCAD',solidcraft:'SolidCraft'}
type Health={freecad?:string,mode?:EngineMode,primary?:Engine,fallback?:Engine,fallbackEnabled?:boolean,
  engines?:Record<Engine,{available:boolean,version?:string,reason?:string}>}
type Evidence={cases?:{name:string,result:string}[],transitionsPassed?:boolean,actualSlots?:number,
  engine?:Engine,engineVersion?:string,fallbackReason?:string,recomputeSuccessful?:boolean,
  drawing?:{validated:boolean,views?:number}}
type Job={id:string,files:Record<string,string>,evidence:Evidence}
function Blueprint({model,dimensions}:{model:Preview,dimensions:boolean}) {
  const {parameters:p,slots}=model
  const slotCount=model.calculations.totalSlots
  const scale=Math.min(560/p.boardWidth,292/p.boardHeight)
  const w=p.boardWidth*scale,h=p.boardHeight*scale
  const x=390-w/2,y=207-h/2
  return <svg className="blueprint-svg" viewBox="0 0 780 410" role="img" aria-label={`Top view: ${slotCount} ${slotCount===1?'slot':'slots'}, ${p.boardWidth} by ${p.boardHeight} millimetres`}>
    <defs>
      <marker id="arrow" markerWidth="7" markerHeight="7" refX="5.5" refY="3.5" orient="auto-start-reverse" markerUnits="userSpaceOnUse"><path d="M0 0L6 3.5L0 7" fill="none" stroke="#486a9a"/></marker>
      <pattern id="minor" width="16" height="16" patternUnits="userSpaceOnUse"><path d="M16 0H0V16" fill="none" stroke="#e6edf6" strokeWidth=".8"/></pattern>
      <pattern id="major" width="80" height="80" patternUnits="userSpaceOnUse"><rect width="80" height="80" fill="url(#minor)"/><path d="M80 0H0V80" fill="none" stroke="#dce7f3"/></pattern>
    </defs>
    <rect width="780" height="410" fill="url(#major)"/>
    <rect x={x} y={y} width={w} height={h} fill="#e3edf9" stroke="#2e507b" strokeWidth="1.55"/>
    {slots.map(([sx,sy],i)=><rect key={i} x={x+sx*scale} y={y+h-(sy+p.slotLength)*scale} width={p.slotWidth*scale} height={p.slotLength*scale} fill="#f8faff" stroke="#466b9b" strokeWidth=".9"><title>{`Slot ${i+1} · X ${number(sx)} mm · Y ${number(sy)} mm`}</title></rect>)}
    {dimensions&&<g className="measure">
      <path d={`M${x} ${y-5}v-27 M${x+w} ${y-5}v-27 M${x-5} ${y}h-33 M${x-5} ${y+h}h-33`} stroke="#85a1c5" fill="none"/>
      <path d={`M${x} ${y-24}h${w} M${x-30} ${y}v${h}`} stroke="#486a9a" fill="none" markerStart="url(#arrow)" markerEnd="url(#arrow)"/>
      <text x={390} y={y-31} textAnchor="middle">{number(p.boardWidth)} mm</text>
      <text transform={`translate(${x-39},207) rotate(-90)`} textAnchor="middle">{number(p.boardHeight)} mm</text>
    </g>}
    <g transform="translate(33 375)" className="measure">
      <path d="M0 -19V0H21" stroke="#486a9a" fill="none"/><circle r="2.5" fill="#486a9a"/><text x="-4" y="-24">Y</text><text x="25" y="4">X</text>
    </g>
    <text className="measure small-svg" x="747" y="379" textAnchor="end">XY PLANE · Z = 0</text>
  </svg>
}

function App() {
  const params=new URLSearchParams(location.search)
  const standalone=location.protocol==='file:'||import.meta.env.MODE==='standalone'
  const demo=params.has('demo')||location.pathname.endsWith('demo.html')||standalone
  const [draft,setDraft]=useState<Input>({...defaults})
  const [current,setCurrent]=useState<Preview>(()=>calculate(defaults))
  const [message,setMessage]=useState('Dimensions are ready to review.')
  const [error,setError]=useState('')
  const [busy,setBusy]=useState('')
  const [health,setHealth]=useState<Health>()
  const [engineMode,setEngineMode]=useState<EngineMode>()
  const [engineEvidence,setEngineEvidence]=useState<Evidence>()
  const version=health?.freecad
  const [id,setId]=useState('')
  const [detailEditor,setDetailEditor]=useState<{source:DesignSource|null}>()
  const [files,setFiles]=useState<Record<string,string>>(demo?downloadable:{})
  const [testResults,setTestResults]=useState<Job['evidence']>()
  const [modelEvidence,setModelEvidence]=useState<number>()
  const [tab,setTab]=useState<'2d'|'3d'>('2d')
  const [dimensions,setDimensions]=useState(true)
  const [expanded,setExpanded]=useState(false)
  const [material,setMaterial]=useState('')
  const viewerDialog=useRef<HTMLDialogElement>(null)
  const [viewerOpen,setViewerOpen]=useState(false)
  const [drawingTab,setDrawingTab]=useState<'views'|'sheet'>('views')
  const projectedCanvases=useRef<HTMLDivElement>(null)
  const sheetUrl=files['pegboard.svg']
  const glb=demo?sampleUrl('pegboard.glb'):files['pegboard.glb']
  const stl=files['pegboard.stl']
  const viewerSource=glb?{url:glb,format:'glb' as const}:stl?{url:stl,format:'stl' as const}:null
  const video=useRef<HTMLDialogElement>(null)
  const upload=useRef<HTMLInputElement>(null)
  useEffect(()=>{if(!demo) api<Health>('/health').then(setHealth).catch(()=>setHealth({}))},[demo])
  const dirty=fields.some(([key])=>String(draft[key])!==String(current.parameters[key]))
  const preferred=engineMode||health?.mode||'auto'
  const c=current.calculations
  const p=current.parameters
  const nextX=c.minBoardWidth+c.columnCount*c.pitchX
  const nextY=c.minBoardHeight+c.rowCount*c.pitchY

  function accept(model:Preview) {
    const before=current.calculations, after=model.calculations
    const changes=[['Column',before.columnCount,after.columnCount,'width',after.minBoardWidth,after.pitchX],['Row',before.rowCount,after.rowCount,'height',after.minBoardHeight,after.pitchY]] as const
    const note=changes.filter(([,a,b])=>a!==b).map(([axis,a,b,side,min,pitch])=>`${axis} count ${a} → ${b}. The ${side} threshold for ${Math.max(a,b)} ${axis.toLowerCase()}s is ${number(min+(Math.max(a,b)-1)*pitch)} mm.`).join(' ')
    setCurrent(model);setDraft(model.parameters);setMessage(note||'Parameters applied. The pattern count is unchanged.');setError('')
    setModelEvidence(undefined);setEngineEvidence(undefined)
    if (!demo) setFiles(old=>Object.fromEntries(Object.entries(old).filter(([name])=>!modelFiles.includes(name))))
  }
  async function act(label:string, callback:()=>Promise<void>) {
    setBusy(label);setError('')
    try {await callback()}
    catch (err) {setError(err instanceof Error?err.message:String(err))}
    finally {setBusy('')}
  }
  function readDraft() {
    return Object.fromEntries(fields.map(([key])=>[key,String(draft[key]).trim()===''?NaN:Number(draft[key])])) as Parameters
  }
  async function apply(value=readDraft()) {
    const local=calculate(value)
    const result=demo?local:await api<Preview>('/parameters/validate',value)
    const sources=Object.fromEntries(fields.filter(([key])=>value[key]===current.parameters[key]&&current.sources?.[key])
      .map(([key])=>[key,current.sources![key]]))
    if(current.sources?.holeSpacing) sources.holeSpacing=current.sources.holeSpacing
    accept({...result,sources,detailParameters:current.detailParameters})
  }
  function cad(action:'model'|'drawing'|'tests') {
    if(demo){
      setMessage(action==='tests'?'Showing the recorded FreeCAD acceptance results for the sample.':'Sample exports are available below. Use the full app to generate files for your parameters.')
      if(action==='tests') setTestResults({cases:[{name:'Smallest valid board',result:'PASS'},{name:'Nominal board',result:'PASS'},{name:'Wider board',result:'PASS'}],transitionsPassed:true})
      return
    }
    if(dirty&&action!=='tests') {setError('Apply your edited parameters before generating CAD or drawings.');return}
    void act(action==='model'?'Recomputing CAD':action==='drawing'?'Building the drawing sheet':'Running the CAD acceptance cases',async ()=>{
      const model_id=id||undefined
      const today=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10)
      let result:Job
      if(action==='tests'){
        result=await api<Job>('/tests/run',{engine:engineMode})
        setTestResults(result.evidence)
        setMessage('Acceptance run complete. See case results and measured geometry in the validation report.')
      } else {
        const body={parameters:p,model_id,engine:engineMode,sources:current.sources,detail_parameters:current.detailParameters}
        result=action==='drawing'
          ?await api<Job>('/drawing/generate',{...body,metadata:{date:today,material:material.trim()||'Unspecified'}})
          :await api<Job>(id?'/model/recompute':'/model/generate',body)
        setId(result.id);setModelEvidence(result.evidence.actualSlots)
        setMessage(action==='drawing'?'Four-view drawing and CAD files are ready.':'Solid verified against the spreadsheet and opening geometry.')
      }
      setEngineEvidence(result.evidence)
      setFiles(old=>({...Object.fromEntries(Object.entries(old).filter(([name])=>action==='tests'?!name.startsWith('case_'):!modelFiles.includes(name))),...result.files}))
    })
  }
  async function loadFile(file:File) {
    if(demo){
      if(!file.name.toLowerCase().endsWith('.csv')) throw Error('The interactive demo accepts CSV. Use the full app to upload Excel workbooks.')
      const rows=(await file.text()).replace(/^\uFEFF/,'').split(/\r?\n/).map(line=>line.split(',').map(cell=>cell.trim().replace(/^"|"$/g,'').trim()))
      const values=Object.fromEntries(fields.map(([key])=>{
        const hits=rows.filter(row=>row[0]===key)
        if(hits.length!==1||!hits[0][1]) throw Error(`Enter one value for ${key} in the CSV.`)
        const value=hits[0][1]
        if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value)) {
          throw Error(`Enter a decimal number for ${key} in the CSV.`)
        }
        return [key,Number(value)]
      })) as Parameters
      await apply(values)
    } else {
      const body=new FormData()
      body.append('file',file)
      accept(await api<Preview>('/spreadsheet/upload',body))
    }
  }

  return <>
    <header className="topbar">
      <div className="brand"><div className="logo"><Layers3 size={20}/></div><div>Spreadsheet to Drawing<span>PARAMETRIC CAD WORKSPACE</span></div></div>
      <nav aria-label="Workspace"><a className="nav-active" href={demo?'?demo':'./'}>{demo?'Demo workspace':'Workspace'}</a><a href={standalone?fullAppSetup:demo?'./':'?demo'}>{standalone?'Full app setup':demo?'Local workspace':'Interactive demo'} <ArrowRight size={12}/></a></nav>
      <button className="btn video-button" onClick={()=>video.current?.showModal()}><Play size={15}/> Demo video</button>
    </header>
    <main>
      <section className="hero">
        <div><div className="eyebrow"><span/> MODEL WORKSPACE <small>/</small> PB-001</div><h1>Parametric pegboard</h1><p>Drive a parametric model and manufacturing drawing from spreadsheet dimensions.</p></div>
        <div className="hero-end"><span className="mode"><span className={demo||version||health?.engines?.solidcraft.available?'green':'amber'}/>{demo?'Interactive demo':version?'FreeCAD '+version:health?.engines?.solidcraft.available?'SolidCraft '+health.engines.solidcraft.version:health?'CAD engines offline':'Checking CAD engines'}</span><button className="btn primary" disabled={!!busy} onClick={()=>cad('model')}><Box size={17}/> Generate CAD model</button>
          <button className="btn" disabled={!!busy||!viewerSource}
            title={viewerSource?undefined:'Generate a CAD model to enable the viewer'}
            onClick={()=>{setDrawingTab(sheetUrl?'sheet':'views');viewerDialog.current?.showModal();setViewerOpen(true)}}><Eye size={16}/> View in browser</button>
          {!demo&&id&&viewerSource&&<button className="btn" disabled={!!busy} onClick={()=>setDetailEditor({
            source:{sourceModelId:id,parameters:current.parameters,sources:current.sources||{},detailParameters:current.detailParameters,mesh:viewerSource}
          })}>Create Detailed Product Design</button>}
          {!demo&&<button className="btn small-btn" onClick={()=>setDetailEditor({source:null})}>Saved detailed designs</button>}
        </div>
      </section>
      {demo&&<aside className="demo-note">
        <CircleHelp size={16} aria-hidden="true"/>
        <div>
          Edit dimensions or select a case. The browser demo includes recorded FreeCAD sample exports.
          <details className="demo-engine-help">
            <summary>How CAD engine switching works</summary>
            <p>To generate custom CAD files, run the full app with a CAD engine installed. Auto tries FreeCAD first
              and retries a failed CAD operation once with SolidCraft 0.45.0. You can also select either engine manually.</p>
            <p><a href={setupGuide+'#cad-engine-switching'}>CAD engine setup and supported exports</a></p>
          </details>
        </div>
      </aside>}
      {!demo&&<section className="panel engine-panel" aria-label="CAD engine">
        <div className="engine-controls">
          <label>CAD engine <select aria-label="CAD engine mode" disabled={!!busy} value={preferred}
            onChange={e=>setEngineMode(e.target.value as EngineMode)}>
            <option value="auto">Auto</option><option value="freecad">FreeCAD only</option><option value="solidcraft">SolidCraft only</option>
          </select></label>
          {(['freecad','solidcraft'] as const).map(engine=>{
            const status=health?.engines?.[engine]
            return <span key={engine} title={status?.reason}>{engineNames[engine]} {status?.available?status.version:health?'unavailable':'checking'}</span>
          })}
        </div>
        {preferred==='auto'&&health?.primary&&<p>Preferred engine: {engineNames[health.primary]}{health.fallbackEnabled&&health.fallback? ` · Fallback: ${engineNames[health.fallback]}`:''}</p>}
        {engineEvidence?.engine&&<p aria-live="polite">Last verified engine: <strong>{engineNames[engineEvidence.engine]} {engineEvidence.engineVersion}</strong>
          {engineEvidence.recomputeSuccessful&&' · Recompute passed'}{engineEvidence.drawing?.validated&&' · Drawing validated'}
          {engineEvidence.fallbackReason&&<span className="fallback-reason">Fallback reason: {engineEvidence.fallbackReason}</span>}
        </p>}
      </section>}
      <div className="workspace">
        <section className="panel params">
          <div className="panel-head"><div className="icon-tile"><FileSpreadsheet size={19}/></div><div><h2>Parameters</h2><p>Spreadsheet inputs in millimetres</p></div></div>
          <div className="filebar">
            <input ref={upload} type="file" accept={demo?'.csv':'.xlsx,.csv'} hidden onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void act('Reading spreadsheet',()=>loadFile(file))}}/>
            <button className="btn small-btn" disabled={!!busy} onClick={()=>upload.current?.click()}><Upload size={14}/> Load spreadsheet</button>
            <a className="template" title={demo?'Download CSV template':'Download Excel template'} href={sampleUrl(demo?'pegboard_parameters.csv':'pegboard_parameters.xlsx')} download={demo?'pegboard_parameters.csv':'pegboard_parameters.xlsx'}><ArrowDownToLine size={14}/> {demo?'CSV template':'Excel template'}</a>
          </div>
          {demo&&<div className="casebar">{cases.map(([name,w,h])=><button key={name} className="btn small-btn" onClick={()=>void act('Loading demo case',()=>apply({...defaults,boardWidth:w,boardHeight:h}))}>{name}</button>)}</div>}
          <form onSubmit={e=>{e.preventDefault();void act('Validating dimensions',()=>apply())}}>
            <div className="table-head"><span>PARAMETER</span><span>VALUE</span><span>UNIT</span></div>
            {fields.map(([key,label,hint],i)=><label key={key} className={`field ${i===3?'field-break':''}`}>
              <span className="field-name">{label}<small>{hint}</small></span>
              <input type="number" step="any" value={draft[key]} onChange={e=>setDraft({...draft,[key as Key]:e.target.value})} aria-label={label}/>
              <span className="units">mm</span>
            </label>)}
            <div className="param-footer"><button className="btn primary" type="submit" disabled={!!busy}><Check size={16}/> Apply parameters</button><button className="textbtn" type="button" disabled={!!busy} onClick={()=>void act('Restoring defaults',()=>apply(defaults))}><RotateCcw size={14}/> Reset defaults</button></div>
          </form>
        </section>
        <section className={`panel preview ${expanded?'expanded':''}`}>
          <div className="panel-head preview-head"><div className="icon-tile"><ScanLine size={19}/></div><div><h2>Model preview</h2><p>PB-001 · Rectangular through-slots</p></div>
            <div className="view-controls"><div className="segmented" role="group" aria-label="Preview view"><button aria-pressed={tab==='2d'} onClick={()=>setTab('2d')}>2D Top</button><button aria-pressed={tab==='3d'} onClick={()=>setTab('3d')}>3D Orbit</button></div><button className="square" onClick={()=>setExpanded(!expanded)} aria-label={expanded?'Close expanded preview':'Expand preview'}>{expanded?<X size={17}/>:<Maximize2 size={16}/>}</button></div>
          </div>
          <div className="preview-canvas">{tab==='2d'? <Blueprint model={current} dimensions={dimensions}/>:<Suspense fallback={<p className="scene">Loading 3D geometry…</p>}><Scene preview={current}/></Suspense>}</div>
          <div className="preview-footer"><div><span className="swatch"/> Board outline <span className="swatch slot"/> Through-slot</div><label><input type="checkbox" checked={dimensions} onChange={e=>setDimensions(e.target.checked)}/> Dimensions</label></div>
          <div className="status" aria-live="polite"><span className={error?'danger-icon':'ok-icon'}>{busy?<LoaderCircle size={15} className="spin"/>:error?<X size={15}/>:<Check size={15}/>}</span><div><strong>{busy|| (error?'Action could not complete':dirty?'Edits are pending':modelEvidence!==undefined?`Verified ${engineEvidence?.engine?engineNames[engineEvidence.engine]:'CAD'} solid`:'Valid parameter layout')}</strong><p>{error|| (dirty?'Apply changes to update the last valid preview.':message)}</p></div></div>
        </section>
      </div>
      <div className="lower">
        <section className="panel calculations">
          <div className="panel-head"><div className="icon-tile"><Activity size={19}/></div><div><h2>Pattern calculations</h2><p>Derived from the applied dimensions</p></div></div>
          <div className="metrics">{[['Rows',c.rowCount],['Columns',c.columnCount],['Total slots',c.totalSlots]].map(([label,n])=><div key={label}><small>{label}</small><strong>{n}</strong></div>)}</div>
          <div className="facts">{[['Horizontal pitch',c.pitchX],['Vertical pitch',c.pitchY],['Right clearance',c.rightClearance],['Top clearance',c.topClearance],['Minimum width',c.minBoardWidth],['Minimum height',c.minBoardHeight]].map(([label,n])=><div key={label}><span>{label}</span><b>{number(Number(n))} <small>mm</small></b></div>)}</div>
          <div className="threshold"><Grid2X2 size={16}/><span>Next column at <b>{number(nextX)} mm</b> width · Next row at <b>{number(nextY)} mm</b> height</span></div>
          <details><summary>How the pattern is calculated <ChevronDown size={14}/></summary><p>Pitch is the slot size plus the spacing gap on each axis. The first slot starts at the left and bottom edge margins. Another slot fits when the board span reaches twice the margin plus one slot and the required number of pitches.</p></details>
        </section>
        <section className="panel exports">
          <div className="panel-head"><div className="icon-tile"><FileText size={19}/></div><div><h2>Drawings &amp; exports</h2><p>Native CAD, drawing sheets and validation evidence</p></div></div>
          <div className="export-body">
            {!demo&&<label className="material-label">Drawing material <input value={material} maxLength={48} onChange={e=>setMaterial(e.target.value)} placeholder="Unspecified"/></label>}
            <div className="export-actions"><button className="btn primary" disabled={!!busy} onClick={()=>cad('drawing')}><FileText size={16}/> Generate 2D drawing</button><button className="btn" disabled={!!busy} onClick={()=>cad('tests')}><ClipboardCheck size={16}/> Run three-case tests</button></div>
            <div className="filechips">{resultFiles.map((filename,i)=>filename==='pegboard.sc'&&!files[filename]?null:files[filename]?<a className="btn small-btn" href={files[filename]} download={filename} key={filename}><ArrowDownToLine size={14}/>{formatNames[i]}</a>:<button disabled key={filename} className="btn small-btn">{formatNames[i]}</button>)}</div>
            {testResults?.cases&&<div className="test-results">{testResults.cases.map(row=><div key={row.name}><span>{row.name}</span><b className={row.result==='PASS'?'pass':'failure'}>{row.result}</b></div>)}<p>Row and column transitions {testResults.transitionsPassed?'passed':'failed'}.</p></div>}
            <div className="reports">{files['pegboard_test_log.csv']&&<a href={files['pegboard_test_log.csv']} download="pegboard_test_log.csv"><ArrowDownToLine size={15}/> Download test log</a>}{files['validation_report.json']&&<a href={files['validation_report.json']} download="validation_report.json">JSON report</a>}{[1,2,3].map(i=>['FCStd','sc'].map(ext=>{
              const name=`case_${i}.${ext}`
              return files[name]&&<a key={name} href={files[name]} download={name}>Case {i} {ext==='sc'?'SolidCraft':'FCStd'}</a>
            }))}</div>
          </div>
        </section>
      </div>
      <footer>Spreadsheet to Drawing <span>Millimetres · XY datum · Parametric CAD</span></footer>
    </main>
    <dialog aria-labelledby="cad-viewer-title" ref={viewerDialog} className="video-dialog cad-viewer"
      onClose={()=>{setViewerOpen(false);setDrawingTab('views')}}>
      <div className="panel-head">
        <div><h2 id="cad-viewer-title">3D CAD model</h2>
          <p>{demo?'Nominal SolidCraft sample · 300 × 200 mm · 80 slots':viewerSource?.format==='glb'?'SolidCraft GLB':'FreeCAD STL'} · Drag to orbit, scroll to zoom</p>
        </div>
        <button className="square" aria-label="Close CAD viewer" onClick={()=>viewerDialog.current?.close()}><X size={18}/></button>
      </div>
      {viewerOpen&&viewerSource&&<div className="review-panes">
        <section aria-labelledby="review-3d-title" className="review-pane review-3d">
          <div className="review-pane-heading"><h3 id="review-3d-title">Interactive 3D</h3></div>
          <div className="cad-viewer-canvas">
            <Suspense fallback={<p role="status">Loading the CAD viewer…</p>}>
              <Scene source={viewerSource} projections={projectedCanvases}/>
            </Suspense>
          </div>
          <div className="review-downloads">
            <a className="template" href={viewerSource.url} download={`pegboard.${viewerSource.format}`}>
              <ArrowDownToLine size={15}/> Download {viewerSource.format.toUpperCase()}
            </a>
            {files['pegboard.step']&&<a className="template" href={files['pegboard.step']} download="pegboard.step">Download STEP</a>}
          </div>
        </section>
        <section aria-labelledby="review-views-title" className="review-pane">
          <div className="review-pane-heading"><h3 id="review-views-title">2D and isometric views</h3></div>
          <DrawingReview sheetUrl={sheetUrl} tab={drawingTab} setTab={setDrawingTab} projections={projectedCanvases}/>
          <div className="review-downloads">
            {sheetUrl&&<a className="template" href={sheetUrl} download="pegboard.svg"><ArrowDownToLine size={15}/> Download SVG</a>}
            {files['pegboard.pdf']&&<a className="template" href={files['pegboard.pdf']} download="pegboard.pdf">Download PDF</a>}
            {!sheetUrl&&<span>Generate a 2D drawing to preview the dimensioned sheet.</span>}
          </div>
        </section>
        <section aria-labelledby="review-details-title" className="review-pane review-details">
          <div className="review-pane-heading"><h3 id="review-details-title">Product characteristics</h3></div>
          <ProductDetails model={demo?nominalPreview:current}/>
        </section>
      </div>}
    </dialog>
    {detailEditor&&<DetailedDesign initial={detailEditor.source} onClose={()=>setDetailEditor(undefined)}/>}
    <dialog aria-label="Spreadsheet to Drawing walkthrough" ref={video} onClose={()=>video.current?.querySelector('video')?.pause()} className="video-dialog">
      <div className="panel-head"><div className="icon-tile"><Play size={19}/></div><div><h2>Spreadsheet to Drawing walkthrough</h2><p>Inputs, CAD recomputation, drawings and test evidence</p></div><button className="square" onClick={()=>video.current?.close()} aria-label="Close video"><X size={18}/></button></div>
      <video controls preload="none" playsInline src={sampleUrl('walkthrough.mp4')}><track src={captionUrl} kind="captions" srcLang="en" label="English" default/></video>
      <a className="template video-download" href={sampleUrl('walkthrough.mp4')} download="walkthrough.mp4"><ArrowDownToLine size={15}/> Download video</a>
    </dialog>
  </>
}
createRoot(document.getElementById('root')!).render(<App/>)
