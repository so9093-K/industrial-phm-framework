/** Unsubmitted questions stay in this page's memory, scoped to their exact analysis. */
const drafts = new Map<string,string>();
export const questionDraft = (scope:string):string => drafts.get(scope)??"";
export function keepQuestionDraft(scope:string, text:string):void {
  drafts.delete(scope);
  if(text.trim())drafts.set(scope,text);
  if(drafts.size>64)drafts.delete(drafts.keys().next().value!);
}
