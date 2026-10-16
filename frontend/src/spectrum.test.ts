import assert from "node:assert/strict";
import {test} from "node:test";
import {defaultSpans,parseAcquisition,parseSpectrum,type Spans} from "./spectrum.ts";
const acq={source:"src",binding:"binding",first:1,last:30,count:30};
const spans:Spans={a:{from:1,to:15},b:{from:16,to:30}};
const spectrum=()=>({
 schema_version:1,asset_id:"motor",kind:"acquisition",sampling_rate_hz:12000,segment:1024,
 frequencies:[0,100,200],
 acquisitions:{a:[1,15],b:[16,30]},
 channels:[{channel:"R",label:"vibration R",a:[0.1,0.2,0.3],b:[0.1,0.3,0.5],
   band_changes:[{from_hz:0,to_hz:100,change_db:3.2}]}],
});
test("source identity and acquisition ordinal boundaries",()=>{
 const opts={schema_version:1,asset_id:"motor",history:null,
  acquisition:{source_id:"src",binding_id:"binding",first:1,last:30,count:30}};
 assert.equal(parseAcquisition(opts,"motor")?.source,"src");
 assert.throws(()=>parseAcquisition(opts,"other"),/다른 설비/);
 assert.deepEqual(defaultSpans(acq),spans);
});
test("Welch arrays must align with frequency bins and correct ranges",()=>{
 const data=parseSpectrum(spectrum(),"motor",acq,spans);
 assert.equal(data.channels[0].a.length,3);
 assert.equal(data.used.a[1],15);
 assert.equal(data.channels[0].bands[0].changeDb,3.2);
 const wrong=spectrum();wrong.acquisitions.b=[999];
 assert.throws(()=>parseSpectrum(wrong,"motor",acq,spans),/요청하지 않은/);
});
test("unreliable waveform shape does not produce a plausible graph",()=>{
 const wrong=spectrum();wrong.channels[0].b=[0.1,0.2];
 assert.throws(()=>parseSpectrum(wrong,"motor",acq,spans),/일치하지/);
 const negative=spectrum();negative.channels[0].a=[-1,0.2,0.3];
 assert.throws(()=>parseSpectrum(negative,"motor",acq,spans),/일치하지/);
});
