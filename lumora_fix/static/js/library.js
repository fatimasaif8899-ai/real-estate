let currentBookId=null;
function hide(el){if(el)el.style.display="none";}
function show(el,display="inline-flex"){if(el)el.style.display=display;}
function setHref(el,href){if(el){el.href=href||"#"; if(!href)hide(el); else show(el,"inline-flex");}}
async function openBookModal(id){
  const modal=document.getElementById("bookModal"); if(!modal)return;
  const res=await fetch("/api/book/"+id); if(!res.ok){return;}
  const b=await res.json(); currentBookId=b.id;
  const cover=document.getElementById("modalCover"); if(cover)cover.src=b.cover_url||"";
  document.getElementById("modalAuthor").textContent=b.author_name||"Unknown author";
  document.getElementById("modalTitle").textContent=b.title||"";
  document.getElementById("modalDesc").textContent=b.description||"No description available.";
  const fields={modalYear:b.pub_year||"—",modalLang:b.language||"—",modalSource:b.source_name||"—",modalLicense:b.license_info||"—",modalIsbn:b.isbn||"—",modalPublisher:b.publisher||"—"};
  Object.entries(fields).forEach(([id,v])=>{const e=document.getElementById(id);if(e)e.textContent=v;});
  const read=document.getElementById("modalRead"); if(read){read.href="/read/"+b.id;show(read,"inline-flex");read.onclick=()=>trackRead(b.id);}
  const pdf=document.getElementById("modalPdf"); if(pdf){setHref(pdf,b.pdf_url); if(b.pdf_url)pdf.onclick=()=>trackDownload(b.id,"pdf");}
  const epub=document.getElementById("modalEpub"); if(epub){setHref(epub,b.epub_url); if(b.epub_url)epub.onclick=()=>trackDownload(b.id,"epub");}
  const save=document.getElementById("saveBtn"), unsave=document.getElementById("unsaveBtn");
  if(save)save.onclick=()=>saveBook(b.id); if(unsave)unsave.onclick=()=>unsaveBook(b.id);
  if(b.saved){hide(save);show(unsave);}else{show(save);hide(unsave);}
  const edit=document.getElementById("modalEdit"); if(edit)edit.href="/admin/books/"+b.id+"/edit";
  const del=document.getElementById("modalDelete"); if(del){del.onclick=async()=>{const f=new FormData();f.append("csrf_token",window.LUMORA_CSRF);const r=await fetch("/admin/books/"+b.id+"/delete",{method:"POST",body:f});if(r.ok)location.reload();};}
  modal.classList.add("active");
  if(location.pathname==="/library")history.replaceState(null,"","/library?book="+id);
}
function closeBookModal(){document.getElementById("bookModal")?.classList.remove("active");}
async function trackRead(id){await fetch("/track-read/"+id,{method:"POST",headers:{"X-CSRF-Token":window.LUMORA_CSRF}}).catch(()=>{});}
async function trackDownload(id,format){const r=await fetch("/track-download/"+id+"?format="+format,{method:"POST",headers:{"X-CSRF-Token":window.LUMORA_CSRF}});if(r.status===401)location.href="/login";}
async function saveBook(id){const r=await fetch("/save-book/"+id,{method:"POST",headers:{"X-CSRF-Token":window.LUMORA_CSRF}});if(r.status===401){location.href="/login";return;}if(r.ok){hide(document.getElementById("saveBtn"));show(document.getElementById("unsaveBtn"));}}
async function unsaveBook(id){const r=await fetch("/unsave-book/"+id,{method:"POST",headers:{"X-CSRF-Token":window.LUMORA_CSRF}});if(r.status===401){location.href="/login";return;}if(r.ok){show(document.getElementById("saveBtn"));hide(document.getElementById("unsaveBtn"));}}
async function shareBook(){const url=location.origin+"/library?book="+currentBookId;if(navigator.share){await navigator.share({title:"LUMORA Book",url});}else if(navigator.clipboard){await navigator.clipboard.writeText(url);}}
function exportMetadata(){if(currentBookId)location.href="/export/"+currentBookId;}
document.addEventListener("DOMContentLoaded",()=>{const params=new URLSearchParams(location.search);const id=params.get("book");if(id&&/^\d+$/.test(id))openBookModal(Number(id));});
