import { mount } from "svelte";
import App from "./App.svelte";
import "./styles.css";

async function start() {
  if(import.meta.env.MODE==="showcase"){
    try{await (await import("./showcase/runtime")).installSnapshot();}
    catch{
      document.getElementById("app")!.textContent="체험 데이터를 불러오지 못했습니다. HTTP 서버에서 전체 체험 폴더를 열어 주세요.";
      return;
    }
  }
  mount(App, { target: document.getElementById("app")! });
}
void start();
