'use strict';
// Immutable submission snapshots keep retries and late responses separate from current drafts.
(function(root){
  const context=typeof module==='object'&&module.exports?require('./conversation-context.js'):root.PlantConversationContext;
  function freeze(value){if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
  const api={
    applyContext:context.apply,
    scope(thread,fallback){if(fallback?.collectionId==='personal')return fallback;const submitted=thread?.messages.findLast(m=>m.submission)?.submission;if(thread?.sampleScope?.collectionId==='personal'||submitted?.collection_id==='personal')return fallback;return thread?.sampleScope||(submitted?{profile:submitted.profile,questionId:submitted.example_id}:fallback);},
    submission(thread,scope,options={}){return Object.freeze({request_id:crypto.randomUUID(),thread_id:thread.id,text:options.text??thread.draft,input_version:thread.inputVersion||0,profile:scope.profile,example_id:scope.questionId||'',collection_id:scope.collectionId||'samples',history:Object.freeze(thread.messages.filter(m=>m.kind==='user').slice(-4).map(m=>m.text)),context:freeze(context.snapshot(thread,scope)),...(options.selection?{context_selection:options.selection}:{}),...(options.pendingTarget?{pending_target:options.pendingTarget}:{}),...(options.inspect===true?{inspect:true}:{})});},
    complete(thread,submission){const unchanged=!thread.deletedAt&&thread.id===submission.thread_id&&thread.draft===submission.text&&(thread.inputVersion||0)===submission.input_version;if(unchanged)thread.draft='';return unchanged;},
  };
  if(typeof module==='object'&&module.exports)module.exports=api;else root.PlantChatState=api;
})(typeof window==='undefined'?null:window);
