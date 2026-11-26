export class ApiError extends Error {
  constructor(message:string, readonly feature?:string){super(message)}
}

export async function api<T>(path:string,body?:unknown):Promise<T>{
  const response=await fetch('/api'+path,body===undefined?undefined:{method:'POST',
    ...(body instanceof FormData?{body}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})})
  const result=await response.json()
  if(!response.ok){
    const detail=result.detail
    if(typeof detail==='string') throw new ApiError(detail)
    if(Array.isArray(detail)) throw new ApiError(detail.map((d:{loc:string[],msg:string})=>d.loc.slice(1).join('.')+' '+d.msg).join(' · '))
    throw new ApiError(detail?.message||'The API returned an error.',detail?.feature)
  }
  return result
}
