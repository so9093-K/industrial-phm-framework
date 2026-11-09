import {peakSummary,frequencyText} from "./spectrum.ts";
import assert from "node:assert/strict";
import {test} from "node:test";
import {defaultSpans,parseAcquisition,parseSpectrum,peakFrequencies,type Spans} from "./spectrum.ts";
const acq={source:"src",binding:"binding",first:1,last:30,count:30};
const spans:Spans={a:{from:1,to:15},b:{from:16,to:30}};
const spectrum=()=>({
 schema_version:1,asset_id:"motor",kind:"acquisition",sampling_rate_hz:12000,segment:1024,
 frequencies:[0,100,200],
 acquisitions:{a:[1,15],b:[16,30]},
 channels:[{channel:"R",label:"vibration R",a:[0.1,0.2,0.3],b:[0.1,0.3,0.5],
   band_changes:[{from_hz:0,to_hz:100,change_db:3.2}],power_ratio:1.8,
   band_shares:[{from_hz:0,to_hz:100,a:0.4,b:0.3},{from_hz:100,to_hz:200,a:0.6,b:0.7}]}],
});
test("source identity and acquisition ordinal boundaries",()=>{
 const opts={schema_version:1,asset_id:"motor",history:null,
  acquisition:{source_id:"src",binding_id:"binding",first:1,last:30,count:30}};
 assert.equal(parseAcquisition(opts,"motor")?.source,"src");
 assert.throws(()=>parseAcquisition(opts,"other"),/다른 설비/);
 // The first 30% against the last 30% of the acquisitions.
 assert.deepEqual(defaultSpans(acq),{a:{from:1,to:9},b:{from:22,to:30}});
 assert.deepEqual(defaultSpans({...acq,last:2,count:2}),{a:{from:1,to:1},b:{from:2,to:2}});
});
test("Welch arrays must align with frequency bins and correct ranges",()=>{
 const data=parseSpectrum(spectrum(),"motor",acq,spans);
 assert.equal(data.channels[0].a.length,3);
 assert.equal(data.used.a[1],15);
 assert.equal(data.channels[0].bands[0].changeDb,3.2);
 const wrong=spectrum();wrong.acquisitions.b=[999];
 assert.throws(()=>parseSpectrum(wrong,"motor",acq,spans),/고르지 않은/);
});
test("unreliable waveform shape does not produce a plausible graph",()=>{
 const wrong=spectrum();wrong.channels[0].b=[0.1,0.2];
 assert.throws(()=>parseSpectrum(wrong,"motor",acq,spans),/일치하지/);
 const negative=spectrum();negative.channels[0].a=[-1,0.2,0.3];
 assert.throws(()=>parseSpectrum(negative,"motor",acq,spans),/일치하지/);
});

test("a full-resolution Welch band can extend above the last DISPLAYED mean bin",()=>{
  const valid=spectrum();
  valid.channels[0].band_changes[0]={from_hz:150,to_hz:250,change_db:3.2};
  assert.equal(parseSpectrum(valid,"motor",acq,spans).channels[0].bands[0].to,250);
  const impossible=spectrum();
  impossible.channels[0].band_changes[0].to_hz=6500; // Nyquist is 6000 Hz.
  assert.throws(()=>parseSpectrum(impossible,"motor",acq,spans),/범위/);
});

test("the strongest frequencies are peaks, strongest first, never the offset at 0 Hz",()=>{
  const frequencies=[0,50,100,150,200,250,300];
  // The 0 Hz offset is largest; the peaks are at 100 Hz and 250 Hz.
  assert.deepEqual(peakFrequencies(frequencies,[9,1,4,2,3,5,1]),[250,100]);
  assert.deepEqual(peakFrequencies(frequencies,[0,0,0,0,0,0,0]),[]);
});


test("a flat spectrum has no peaks and sub-hertz resolution stays non-zero",()=>{
  assert.equal(peakSummary([0,0.125,0.25],[0,0,0]),"뚜렷한 피크 없음");
  assert.equal(peakSummary([0,0.125,0.25],[0,10,0]),"0.125 Hz");
  assert.equal(frequencyText(0.125),"0.125");
  assert.notEqual(frequencyText(0.000001),"0");
});
