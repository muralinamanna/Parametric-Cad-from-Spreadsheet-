import {number} from './model'
import type {Preview} from './model'

export default function ProductDetails({model}:{model:Preview}) {
  const {parameters:p,calculations:c}=model
  const mm=(n:number)=>number(n)+' mm'
  return <>
    <dl className="product-specs">
      <dt>Board (X × Y × Z)</dt><dd>{[p.boardWidth,p.boardHeight,p.boardThickness].map(number).join(' × ')} mm</dd>
      <dt>Slot (width × length)</dt><dd>{number(p.slotWidth)} × {number(p.slotLength)} mm</dd>
      <dt>Slot count</dt><dd>{c.totalSlots} ({c.rowCount} rows × {c.columnCount} columns)</dd>
      <dt>Horizontal pitch</dt><dd>{mm(c.pitchX)}</dd>
      <dt>Vertical pitch</dt><dd>{mm(c.pitchY)}</dd>
      <dt>Minimum edge margin</dt><dd>{mm(p.edgeMargin)}</dd>
      <dt>Slot spacing</dt><dd>{mm(p.slotSpacing)}</dd>
      <dt>Right edge clearance</dt><dd>{mm(c.rightClearance)}</dd>
      <dt>Top edge clearance</dt><dd>{mm(c.topClearance)}</dd>
    </dl>
    <h4>Definitions</h4>
    <dl className="product-definitions">
      <dt>Datum</dt><dd>Origin of the board at its lower-left corner. X is width, Y is height and Z is thickness.</dd>
      <dt>Through-slot</dt><dd>A rectangular opening that passes through the full board thickness.</dd>
      <dt>Pitch</dt><dd>Centre-to-centre distance between adjacent slots in the same row or column.</dd>
      <dt>Slot spacing</dt><dd>Material gap from the edge of one slot to the next.</dd>
      <dt>Edge clearance</dt><dd>Shortest distance from the nearest slot boundary to a board edge.</dd>
    </dl>
  </>
}
