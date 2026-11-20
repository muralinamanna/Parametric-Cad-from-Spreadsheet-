export const defaults = {boardWidth:300,boardHeight:200,boardThickness:6,edgeMargin:12,slotWidth:6,slotLength:25,slotSpacing:12}
export type Key = keyof typeof defaults
export type Parameters = Record<Key, number>
export type Input = Record<Key, string|number>
export type Calculations = ReturnType<typeof calculate>['calculations']
export type Preview = ReturnType<typeof calculate>
export const fields: [Key,string,string][] = [
  ['boardWidth','Board width','Overall dimension along X'],
  ['boardHeight','Board height','Overall dimension along Y'],
  ['boardThickness','Thickness','Extrusion depth along Z'],
  ['edgeMargin','Edge margin','Minimum material at every edge'],
  ['slotWidth','Slot width','Opening dimension along X'],
  ['slotLength','Slot length','Opening dimension along Y'],
  ['slotSpacing','Slot spacing','Material gap between openings'],
]
export const number = (value:number) => Number(value.toFixed(6)).toString()

export function calculate(parameters:Parameters) {
  const {boardWidth:w,boardHeight:h,boardThickness:t,edgeMargin:m,slotWidth:sw,slotLength:sl,slotSpacing:gap} = parameters
  const e = 1e-7
  if (!Object.values(parameters).every(Number.isFinite)) throw Error('Enter a finite number in every row.')
  if (Math.max(...Object.values(parameters))>1_000_000) throw Error('Dimensions cannot exceed 1,000,000 mm.')
  if (Math.min(t,sw,sl)<=e || m<0 || gap<0) throw Error('Thickness and slot dimensions must exceed 0.0000001 mm. Margin and spacing must be nonnegative.')
  const minBoardWidth=2*m+sw, minBoardHeight=2*m+sl
  const belowMinimum=(span:number, minimum:number)=>span<minimum && minimum-span>Math.max(1e-12,minimum*2e-16)
  if (belowMinimum(w,minBoardWidth) || belowMinimum(h,minBoardHeight)) throw Error(`Minimum board size for these inputs is ${number(minBoardWidth)} × ${number(minBoardHeight)} mm.`)
  const pitchX=sw+gap, pitchY=sl+gap
  const columnCount=Math.floor((w-minBoardWidth+e)/pitchX)+1
  const rowCount=Math.floor((h-minBoardHeight+e)/pitchY)+1
  const totalSlots=columnCount*rowCount
  if (totalSlots>2000) throw Error('This application supports up to 2,000 slots per board.')
  const rightClearance=w-m-sw-(columnCount-1)*pitchX
  const topClearance=h-m-sl-(rowCount-1)*pitchY
  if (Math.min(m,rightClearance,topClearance)<=e || (totalSlots>1 && gap<=e)) throw Error('Distinct enclosed through-slots require positive material around and between the openings.')
  const slots = Array.from({length:totalSlots},(_,i):[number,number] => [m+(i%columnCount)*pitchX,m+Math.floor(i/columnCount)*pitchY])
  return {parameters, calculations:{minBoardWidth,minBoardHeight,pitchX,pitchY,columnCount,rowCount,totalSlots,rightClearance,topClearance,availableWidth:w-2*m,availableHeight:h-2*m}, slots}
}
