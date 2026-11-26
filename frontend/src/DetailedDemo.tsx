import {lazy,Suspense,useEffect,useRef,useState} from 'react'
import {ArrowDownToLine,X} from 'lucide-react'

const Scene=lazy(()=>import('./Scene'))
const stages=['Spreadsheet plate','Add details','Refresh spreadsheet','Invalid pocket'] as const

export default function DetailedDemo({asset,onClose}:{asset:(name:string)=>string,onClose:()=>void}) {
  const modal=useRef<HTMLDialogElement>(null)
  const [stage,setStage]=useState(0)
  useEffect(()=>{modal.current?.showModal()},[])
  const updated=stage>=2, detailed=stage>0, invalid=stage===3
  const sample=updated?'cadrs_refreshed':detailed?'cadrs_initial':'cadrs_base'
  const csv=updated?'cadrs_refreshed_plate.csv':'cadrs_mounting_plate.csv'
  return <dialog className="video-dialog detail-dialog" ref={modal} onClose={onClose} aria-labelledby="offline-detail-title">
    <div className="panel-head">
      <div><h2 id="offline-detail-title">Detailed design demo</h2><p>Offline tour of recorded CADRS builds</p></div>
      <button className="square" aria-label="Close detailed design demo" onClick={()=>modal.current?.close()}><X size={18}/></button>
    </div>
    <div className="detail-actions" role="group" aria-label="Demo stages">
      {stages.map((label,index)=><button key={label} type="button" className={`btn small-btn${stage===index?' primary':''}`}
        aria-pressed={stage===index} onClick={()=>setStage(index)}>{label}</button>)}
    </div>
    <div className="detail-status" role={invalid?'alert':'status'}>
      {invalid?'Pocket depth 9 mm was rejected because the plate is 8 mm thick. The preview and downloads still show the last valid build.':
        updated?'The new spreadsheet increased board width from 120 to 140 mm and mounting-hole pitch from 55 to 65 mm.':
        detailed?'The verified CADRS build applied the four-hole pattern, pocket, and front-edge chamfer.':
        'Start with the spreadsheet plate and its original slots. Select Add details to compare the detailed model.'}
    </div>
    <div className="detail-grid">
      <section className="detail-panel" aria-label="Sample spreadsheet">
        <h3>Spreadsheet values</h3>
        <dl>
          <div><dt>Board width · {updated?140:120} mm</dt><dd>CSV row 2, column B</dd></div>
          <div><dt>Board length · 100 mm</dt><dd>CSV row 3, column B</dd></div>
          <div><dt>Thickness · 8 mm</dt><dd>CSV row 4, column B</dd></div>
          <div><dt>Mounting-hole pitch · {updated?65:55} mm</dt><dd>CSV row 9, column B</dd></div>
        </dl>
        <div className="detail-actions"><a className="btn small-btn" href={asset(csv)} download="mounting_plate.csv"><ArrowDownToLine size={14}/> CSV</a></div>
      </section>
      <section className="detail-panel" aria-label="Sample features">
        <h3>Feature history</h3>
        {detailed?<ol>
          <li><p><strong>Rectangular hole pattern</strong><br/>Four Ø4 mm through-holes. The first centre is at X 8, Y 8 mm. X and Y pitch are bound to the spreadsheet.</p></li>
          <li><p><strong>Rectangular pocket</strong><br/>15 × 8 mm at X 20, Y 50 mm. The successful cut is 2 mm deep.
            {invalid&&<span className="feature-error"> The 9 mm edit failed validation.</span>}</p></li>
          <li><p><strong>Edge chamfer</strong><br/>1 mm on the top front edge.</p></li>
        </ol>:<p>The original model has no detailed features.</p>}
      </section>
      <section className="detail-panel" aria-label="Sample model">
        <h3>{invalid?'Last valid model':'3D preview'}</h3>
        <div className="detail-preview"><Suspense fallback={<p>Loading viewer…</p>}>
          <Scene source={{url:asset(sample+'.stl'),format:'stl'}}/>
        </Suspense></div>
        <div className="detail-actions">
          <a className="btn small-btn" href={asset(sample+'.stl')} download={sample+'.stl'}><ArrowDownToLine size={14}/> STL</a>
          {detailed&&<a className="btn small-btn" href={asset(sample+'.step')} download={sample+'.step'}><ArrowDownToLine size={14}/> STEP</a>}
        </div>
      </section>
    </div>
  </dialog>
}
