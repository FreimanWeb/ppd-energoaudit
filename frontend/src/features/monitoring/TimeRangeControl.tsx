import { useRef } from "react";
import { Button } from "../../shared/ui/Button";
import { Tooltip } from "../../shared/ui/Tooltip";

const formatTime = (value:number) => new Date(value).toLocaleString("ru-RU",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"});
export function TimeRangeControl({domain,viewport,onChange}:{domain:[number,number];viewport:[number,number]|null;onChange:(value:[number,number]|null)=>void}) {
  const drag=useRef<{pointerId:number;x:number;start:number;end:number;width:number}|null>(null);
  const [min,max]=domain;
  const [start,end]=viewport??domain;
  const span=max-min, step=Math.max(1,Math.round(span/1000));
  const change=(value:[number,number])=>onChange(value[0]===min && value[1]===max ? null : value);
  const move=(value:number,duration=end-start)=>{
    const next=Math.max(min,Math.min(max-duration,value));
    change([next,next+duration]);
  };
  return <section className="timeline-time-control" aria-label="Управление временем">
    <div className="time-control-heading"><strong>Временная шкала</strong>
      <Tooltip label="Временная шкала" content="Перетащите границу, чтобы изменить масштаб, или выделенную полосу, чтобы сдвинуть интервал сразу на всех графиках. Кнопка «Весь период» возвращает полный диапазон." />
      <Button variant="secondary" disabled={!viewport} onClick={()=>onChange(null)}>Весь период</Button>
    </div>
    <div className="time-control-track">
      <div className="time-control-selection" style={{left:`${(start-min)/span*100}%`,right:`${(max-end)/span*100}%`}}
        role="slider" tabIndex={viewport?0:-1} aria-label="Положение видимого периода" aria-valuemin={min} aria-valuemax={max-(end-start)} aria-valuenow={start} aria-valuetext={`${formatTime(start)} — ${formatTime(end)}`}
        onPointerDown={event=>{
          if(event.button!==0)return;
          event.preventDefault();
          drag.current={pointerId:event.pointerId,x:event.clientX,start,end,width:event.currentTarget.parentElement!.getBoundingClientRect().width};
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={event=>{
          const initial=drag.current;
          if(initial?.pointerId===event.pointerId)move(initial.start+(event.clientX-initial.x)/initial.width*span,initial.end-initial.start);
        }}
        onPointerUp={event=>{
          drag.current=null;
          if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={()=>{drag.current=null;}}
        onLostPointerCapture={()=>{drag.current=null;}}
        onKeyDown={event=>{
          if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;
          event.preventDefault();
          move(event.key==="Home"?min:event.key==="End"?max-(end-start):start+(event.key==="ArrowLeft"?-step:step));
        }} />
      <input type="range" aria-label="Начало видимого периода" aria-valuetext={formatTime(start)} min={min} max={max} step={step} value={start}
        onChange={event=>change([Math.min(Number(event.target.value),end-step),end])} />
      <input type="range" aria-label="Конец видимого периода" aria-valuetext={formatTime(end)} min={min} max={max} step={step} value={end}
        onChange={event=>change([start,Math.max(Number(event.target.value),start+step)])} />
    </div>
    <div className="time-control-dates"><time dateTime={new Date(start).toISOString()}>{formatTime(start)}</time><time dateTime={new Date(end).toISOString()}>{formatTime(end)}</time></div>
  </section>;
}
