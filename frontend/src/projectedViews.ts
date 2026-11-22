export const projectedViews = [
  {name:'Top', direction:[0,0,1], up:[0,1,0]},
  {name:'Front', direction:[0,-1,0], up:[0,0,1]},
  {name:'Right', direction:[1,0,0], up:[0,0,1]},
  {name:'Bottom', direction:[0,0,-1], up:[0,-1,0]},
  {name:'Rear', direction:[0,1,0], up:[0,0,1]},
  {name:'Left', direction:[-1,0,0], up:[0,0,1]},
  {name:'Isometric', direction:[1,-1,1], up:[0,0,1]},
] as const
