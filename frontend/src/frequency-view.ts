import type {BandShare, SpectrumChannel} from "./spectrum.ts";
export type FrequencyRange = {from:number;to:number};
export const frequencyLabel=(value:number)=>value.toLocaleString("ko-KR",{maximumSignificantDigits:4});

/** A band's energy share is a different quantity from the total energy ratio. */
export function comparisonBand(channel:SpectrumChannel,from:number|null=null):BandShare|null {
  return channel.shares.find(band=>band.from===from)
    ?? [...channel.shares].sort((a,b)=>Math.abs(b.b-b.a)-Math.abs(a.b-a.a))[0] ?? null;
}
export function aroundBand(band:FrequencyRange,nyquist:number):FrequencyRange {
  const padding=Math.max(band.to-band.from,nyquist/200);
  return {from:Math.max(0,band.from-padding),to:Math.min(nyquist,band.to+padding)};
}
/** Keep this reference over the FULL A/B arrays when the frequency axis is zoomed. */
export function relativePower(values:number[],reference:number,floor=-60):number[] {
  return values.map(value=>reference>0?Math.max(floor,10*Math.log10(Math.max(value,1e-300)/reference)):floor);
}
/** Binned display frequencies are not perfectly equidistant. Preserve their extents in a
 * shared domain rather than stretching selected array indices to fit the chart. */
export function frequencyCells(frequencies:number[],domain:FrequencyRange):{index:number;left:number;width:number}[] {
  if(domain.to<=domain.from)return [];
  return frequencies.flatMap((value,index)=>{
    const previous=frequencies[index-1],next=frequencies[index+1];
    const from=previous===undefined?0:(previous+value)/2,to=next===undefined?Infinity:(value+next)/2;
    const left=Math.max(domain.from,from),right=Math.min(domain.to,to);
    return right>left?[{index,left:(left-domain.from)/(domain.to-domain.from),width:(right-left)/(domain.to-domain.from)}]:[];
  });
}
