import {cpSync,readFileSync,writeFileSync} from "node:fs";
const source=new URL("../../examples/operations/showcase/",import.meta.url);
const target=new URL("../../dist/showcase/",import.meta.url);
const snapshot=JSON.parse(readFileSync(new URL("responses.json",source),"utf8"));
if(snapshot.schema_version!==1||!snapshot.responses)throw new Error("Export showcase API results first");
cpSync(source,new URL("web/scenario/",target),{recursive:true});
writeFileSync(new URL("index.html",target),'<!doctype html><html lang="ko"><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=./web/"><title>Industrial PHM 체험</title><a href="./web/">제품 체험 열기</a></html>');
cpSync(new URL("../../LICENSE",import.meta.url),new URL("LICENSE",target));
writeFileSync(new URL("README.txt",target),"Industrial PHM guided showcase\nServe this directory with an HTTP static server, then open /web/.\nExample: python -m http.server 2720\nSynthetic inputs; read-only recorded application results. No API server or AI model is included.\n");
