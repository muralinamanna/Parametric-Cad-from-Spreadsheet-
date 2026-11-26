import {lazy,Suspense,useEffect,useRef,useState} from 'react'
import {ArrowDown,ArrowUp,Download,Plus,RefreshCw,Save,Trash2,X} from 'lucide-react'
import {api,ApiError} from './api'
import {fields,number} from './model'
import type {Parameters,Preview} from './model'

const Scene=lazy(()=>import('./Scene'))
const featureFields={
  hole:{x:8,y:8,diameter:4},
  pattern:{x:8,y:8,diameter:4,pitchX:40,pitchY:40},
  pocket:{x:20,y:5,width:10,length:5,depth:2},
  fillet:{size:1},chamfer:{size:1},
}
type Kind=keyof typeof featureFields
type Binding={value?:number|null,parameter?:string}
type Feature={id:string,kind:Kind,dimensions:Record<string,Binding>,suppressed:boolean,rows?:number,columns?:number,edge?:string}
type Mesh={url:string,format:'glb'|'stl'}
type Sources=Record<string,string>
export type DesignSource={sourceModelId:string,parameters:Parameters,sources:Sources,detailParameters?:Record<string,number>,mesh?:Mesh}
type Summary={id:string,sourceModelId:string,parameters:Parameters}
type Variant=Summary&{sources:Sources,detailParameters:Record<string,number>,features:Feature[],files:Record<string,string>}
const labels:Record<Kind,string>={hole:'Through hole',pattern:'Rectangular hole pattern',pocket:'Rectangular pocket',fillet:'Edge fillet',chamfer:'Edge chamfer'}
const dimensions:Record<string,string>={x:'X position',y:'Y position',diameter:'Diameter',pitchX:'X pitch',pitchY:'Y pitch',width:'Width',length:'Length',depth:'Depth',size:'Size'}
const edges=[['top-front','Top front edge'],['top-back','Top rear edge'],['top-left','Top left edge'],['top-right','Top right edge']]
function featureId(){
  // The identifier is local to one ordered recipe.
  return 'feature-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2)
}
function describe(summary:Summary){
  const {boardWidth:w,boardHeight:h,boardThickness:t}=summary.parameters
  return `${w} × ${h} × ${t} mm · ${summary.id.slice(0,8)}`
}

export default function DetailedDesign({initial,onClose}:{initial:DesignSource|null,onClose:()=>void}){
  const modal=useRef<HTMLDialogElement>(null)
  const fileInput=useRef<HTMLInputElement>(null)
  const [source,setSource]=useState(initial)
  const [saved,setSaved]=useState<Summary[]>([])
  const [selected,setSelected]=useState('')
  const [features,setFeatures]=useState<Feature[]>([])
  const [kind,setKind]=useState<Kind>('pattern')
  const [latest,setLatest]=useState<Variant>()
  const [pending,setPending]=useState(false)
  const [notice,setNotice]=useState('')
  const [failure,setFailure]=useState<{message:string,feature?:string}>()
  const [changes,setChanges]=useState<string[]>([])
  useEffect(()=>{
    modal.current?.showModal()
    let active=true
    api<Summary[]>('/details').then(records=>{if(active)setSaved(records)}).catch(err=>{
      if(active)setFailure({message:err.message})
    })
    return ()=>{active=false}
  },[])
  const dirty=!!latest&&(JSON.stringify(latest.features)!==JSON.stringify(features)||
    JSON.stringify(latest.parameters)!==JSON.stringify(source?.parameters)||
    JSON.stringify(latest.sources)!==JSON.stringify(source?.sources)||
    JSON.stringify(latest.detailParameters)!==JSON.stringify(source?.detailParameters||{}))
  const bindingValues:Record<string,number>={...source?.parameters,...source?.detailParameters}
  const bindingFields:[string,string][]=[...fields.map(([key,label]):[string,string]=>[key,label]),
    ...(source?.detailParameters?.holeSpacing!==undefined?[['holeSpacing','Mounting hole pitch'] as [string,string]]:[])]
  const mesh:Mesh|undefined=latest?{format:'stl',url:latest.files['detailed.stl']}:source?.mesh

  async function run(task:()=>Promise<void>){
    setPending(true);setFailure(undefined);setNotice('')
    try {await task()}
    catch(error){
      setFailure({message:error instanceof Error?error.message:String(error),feature:error instanceof ApiError?error.feature:undefined})
    } finally {setPending(false)}
  }
  function addFeature(){
    setFeatures([...features,{id:featureId(),kind,suppressed:false,
      ...(kind==='pattern'?{rows:2,columns:2}:{}),
      ...(kind==='fillet'||kind==='chamfer'?{edge:'top-front'}:{}),
      dimensions:Object.fromEntries(Object.entries(featureFields[kind]).map(([key,value])=>[key,{value}]))}])
  }
  function edit(feature:Feature,change:Partial<Feature>){
    setFeatures(features.map(item=>item.id===feature.id?{...item,...change}:item))
  }
  function move(index:number,delta:number){
    const next=[...features]
    const [feature]=next.splice(index,1)
    next.splice(index+delta,0,feature)
    setFeatures(next)
  }
  async function rebuild(input:DesignSource){
    const result=await api<Variant>('/details/build',{source_model_id:input.sourceModelId,
      parameters:input.parameters,sources:input.sources,detail_parameters:input.detailParameters||{},features})
    setSource({...input,parameters:result.parameters,sources:result.sources,detailParameters:result.detailParameters})
    setFeatures(result.features)
    setLatest(result);setNotice('CADRS rebuild successful.')
  }
  async function refresh(file:File){
    if(!source)return
    const data=new FormData()
    data.append('file',file)
    const workbook=await api<Preview>('/spreadsheet/upload',data)
    const updated={...source,parameters:workbook.parameters,sources:workbook.sources||{},detailParameters:workbook.detailParameters||{}}
    const before:Record<string,number>={...source.parameters,...source.detailParameters}
    const after:Record<string,number>={...updated.parameters,...updated.detailParameters}
    const changeValue=(value?:number)=>value===undefined?'missing':number(value)+' mm'
    setChanges([...bindingFields.filter(([key])=>key!=='holeSpacing'),['holeSpacing','Mounting hole pitch']].flatMap(([key,label])=>
      before[key]!==after[key]?[ `${label}: ${changeValue(before[key])} → ${changeValue(after[key])}` ]:[]))
    setSource(updated)
    await rebuild(updated)
  }
  async function openVariant(){
    const record=await api<Variant>('/details/'+selected)
    setSource(record);setFeatures(record.features);setLatest(record);setChanges([])
    setNotice('Saved variant reopened.')
  }
  async function save(){
    if(!latest||dirty)return
    await api('/details/'+latest.id+'/save',{})
    setSaved([latest,...saved.filter(record=>record.id!==latest.id)])
    setSelected(latest.id);setNotice('Editable variant saved.')
  }

  return <dialog className="video-dialog detail-dialog" ref={modal} onClose={onClose} aria-labelledby="detail-title">
    <div className="panel-head">
      <div><h2 id="detail-title">Detailed product design</h2><p>CADRS solid modeling · mm · XY plate datum</p></div>
      <button className="square" aria-label="Close detailed design" onClick={()=>modal.current?.close()}><X size={18}/></button>
    </div>
    <div className="detail-actions">
      {saved.length>0&&<>
        <label>Saved variants <select value={selected} disabled={pending} onChange={e=>setSelected(e.target.value)}>
          <option value="">Select a variant</option>{saved.map(record=><option key={record.id} value={record.id}>{describe(record)}</option>)}
        </select></label>
        <button className="btn small-btn" disabled={!selected||pending} onClick={()=>void run(openVariant)}>Open variant</button>
      </>}
      {source&&<>
        <input ref={fileInput} type="file" accept=".xlsx,.csv" hidden onChange={e=>{
          const next=e.target.files?.[0];e.target.value=''
          if(next)void run(()=>refresh(next))
        }}/>
        <button className="btn small-btn" disabled={pending} onClick={()=>fileInput.current?.click()}><RefreshCw size={15}/> Refresh from spreadsheet</button>
        <button className="btn small-btn primary" disabled={pending} onClick={()=>void run(()=>rebuild(source))}>Rebuild</button>
        <button className="btn small-btn" disabled={pending||!latest||dirty} onClick={()=>void run(save)}><Save size={15}/> Save variant</button>
      </>}
    </div>
    {(pending||failure||notice||dirty)&&<div className="detail-status" role={failure?'alert':'status'}>
      {pending?'Working…':failure?.message||notice||'The feature list has changes to rebuild.'}
      {((failure&&mesh)||dirty)&&<span>Preview and downloads represent the last successful model.</span>}
    </div>}
    {changes.length>0&&<ul className="detail-changes">{changes.map(change=><li key={change}>{change}</li>)}</ul>}
    {source?<div className="detail-grid">
      <section aria-label="Spreadsheet sources" className="detail-panel">
        <h3>Spreadsheet parameters</h3>
        <dl>{bindingFields.map(([key,label])=><div key={key}>
          <dt>{label} · {number(bindingValues[key])} mm</dt><dd>{source.sources[key]||`Field ${key}`}</dd>
        </div>)}</dl>
        <p>Source model <code>{source.sourceModelId.slice(0,8)}</code></p>
      </section>
      <section aria-label="Features" className="detail-panel">
        <h3>Feature history</h3>
        <div className="detail-actions">
          <select aria-label="Feature type" value={kind} onChange={e=>setKind(e.target.value as Kind)} disabled={pending}>
            {Object.entries(labels).map(([key,label])=><option key={key} value={key}>{label}</option>)}
          </select>
          <button className="btn small-btn" disabled={pending||features.length>=40} onClick={addFeature}><Plus size={14}/> Add feature</button>
        </div>
        <ol className="detail-feature-list">{features.map((feature,index)=><li className={failure?.feature===feature.id?'failed-feature':undefined} key={feature.id}>
          <fieldset disabled={pending}>
            <legend>{index+1}. {labels[feature.kind]}{feature.suppressed?' (suppressed)':''}</legend>
            <div className="detail-feature-actions">
              <button className="square" aria-label={`Move feature ${index+1} up`} disabled={index===0} onClick={()=>move(index,-1)}><ArrowUp size={14}/></button>
              <button className="square" aria-label={`Move feature ${index+1} down`} disabled={index===features.length-1} onClick={()=>move(index,1)}><ArrowDown size={14}/></button>
              <button className="square" aria-label={`Delete feature ${index+1}`} onClick={()=>setFeatures(features.filter(item=>item.id!==feature.id))}><Trash2 size={14}/></button>
              <label><input type="checkbox" checked={feature.suppressed} onChange={e=>edit(feature,{suppressed:e.target.checked})}/> Suppress</label>
            </div>
            {failure?.feature===feature.id&&<p className="feature-error">{failure.message}</p>}
            {feature.edge!==undefined&&<label className="detail-field">Reference edge
              <select value={feature.edge} onChange={e=>edit(feature,{edge:e.target.value})}>
                {edges.map(([key,label])=><option key={key} value={key}>{label}</option>)}
              </select>
            </label>}
            {feature.kind==='pattern'&&(['columns','rows'] as const).map(field=><label key={field} className="detail-field">{field==='rows'?'Rows':'Columns'}
              <input type="number" min={1} max={8} step={1} value={feature[field]} onChange={e=>edit(feature,{[field]:Number(e.target.value)})}/>
            </label>)}
            {Object.keys(featureFields[feature.kind]).map(key=>{
              const binding=feature.dimensions[key]||{}
              const name=dimensions[key]
              const parameter=binding.parameter
              const broken=!!parameter&&!Object.hasOwn(bindingValues,parameter)
              const setBinding=(replacement:Binding)=>edit(feature,{dimensions:{...feature.dimensions,[key]:replacement}})
              return <div className="detail-field" key={key}>
                <label htmlFor={feature.id+'-'+key}>{name} (mm)</label>
                <select aria-label={name+' source'} value={parameter||''} onChange={e=>setBinding(e.target.value?{parameter:e.target.value}:{value:parameter&&!broken?bindingValues[parameter]:binding.value??null})}>
                  <option value="">Fixed</option>
                  {broken&&<option value={parameter}>Missing field: {parameter}</option>}
                  {bindingFields.map(([field,label])=><option key={field} value={field}>{label}</option>)}
                </select>
                {parameter?<output className={broken?'feature-error':undefined}>{broken?'Repair binding':number(bindingValues[parameter])+' mm'}</output>:
                  <input id={feature.id+'-'+key} type="number" step="any" value={binding.value??''} onChange={e=>setBinding({value:e.target.value===''?null:Number(e.target.value)})}/>}
              </div>
            })}
          </fieldset>
        </li>)}</ol>
      </section>
      <section aria-label="Detailed model preview" className="detail-panel">
        <h3>{latest?'Last successful detailed model':'Original model'}</h3>
        <div className="detail-preview">
          {mesh?<Suspense fallback={<p>Loading viewer…</p>}><Scene source={mesh}/></Suspense>:<p>Rebuild to display the model.</p>}
        </div>
        {latest&&<div className="detail-actions">{['step','stl'].map(extension=><a key={extension} className="btn small-btn" href={latest.files['detailed.'+extension]} download={'detailed.'+extension}><Download size={14}/> {extension.toUpperCase()}</a>)}</div>}
      </section>
    </div>:<p className="detail-empty">{saved.length?'Select a saved variant to reopen it.':'Generate a CAD model and use Create Detailed Product Design to start a variant.'}</p>}
  </dialog>
}
