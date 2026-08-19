const html=document.documentElement;
const savedTheme=localStorage.getItem("lumora_theme");
if(savedTheme) html.setAttribute("data-theme",savedTheme);

function toggleNav(){document.getElementById("mainNav")?.classList.toggle("open");}

async function setTheme(){
  const next=html.getAttribute("data-theme")==="dark"?"light":"dark";
  html.setAttribute("data-theme",next);
  localStorage.setItem("lumora_theme",next);
  try{
    await fetch("/api/theme",{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":window.LUMORA_CSRF},body:JSON.stringify({theme:next})});
  }catch(e){}
}
document.addEventListener("DOMContentLoaded",()=>{
  document.querySelectorAll("#theme-toggle,#theme-toggle-dash").forEach(b=>b.addEventListener("click",setTheme));
  document.querySelectorAll(".book-card").forEach(el=>el.classList.add("animate-in"));
});


function initCoverUrlPreview(){
  const urlInput=document.getElementById("cover_url");
  const fileInput=document.getElementById("cover_file");
  const preview=document.getElementById("cover-url-preview");
  const image=document.getElementById("cover-preview-image");
  const title=document.getElementById("cover-preview-title");
  const status=document.getElementById("cover-preview-status");
  if(!urlInput||!fileInput||!preview||!image||!title||!status)return;
  let objectUrl=null;
  const setState=(kind,msg,label)=>{
    preview.classList.remove("is-error","is-success");
    if(kind)preview.classList.add(kind);
    status.textContent=msg;
    title.textContent=label;
  };
  const showUrl=()=>{
    const url=urlInput.value.trim();
    if(!url){image.hidden=true;setState("","Paste a direct image URL or choose a cover file to preview it before saving.","Cover preview");return;}
    if(!/^https?:\/\//i.test(url)){image.hidden=true;setState("is-error","Use a direct http:// or https:// image URL.","Invalid cover URL");return;}
    image.hidden=false; image.onload=()=>setState("is-success","Image loaded successfully. This is the cover that will be saved unless you choose a cover file.","Cover preview ready"); image.onerror=()=>{image.hidden=true;setState("is-error","This URL could not be loaded as an image. Use the direct image address, not a Google Images/Pinterest page URL.","Cover URL not usable");}; image.src=url; setState("","Loading image preview…","Checking cover URL");
  };
  urlInput.addEventListener("input",showUrl);
  urlInput.addEventListener("change",showUrl);
  fileInput.addEventListener("change",()=>{
    const file=fileInput.files&&fileInput.files[0];
    if(!file){if(objectUrl){URL.revokeObjectURL(objectUrl);objectUrl=null;}showUrl();return;}
    if(!file.type.startsWith("image/")){image.hidden=true;setState("is-error","Please choose a PNG, JPG, WEBP or GIF image.","Invalid cover file");return;}
    if(objectUrl)URL.revokeObjectURL(objectUrl);
    objectUrl=URL.createObjectURL(file); image.hidden=false; image.onload=()=>setState("is-success","File preview ready. Uploading this file will replace the Cover URL.","Cover file preview"); image.onerror=()=>{image.hidden=true;setState("is-error","The selected image could not be previewed.","Preview unavailable")}; image.src=objectUrl;
  });
  if(urlInput.value.trim())showUrl();
}

document.addEventListener("DOMContentLoaded",initCoverUrlPreview);

// Keep LUMORA decorative videos playing whenever a page is opened/refocused.
// Videos are muted in the templates so modern browsers allow autoplay.
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('video[autoplay]').forEach(function (video) {
    video.muted = true;
    video.setAttribute('muted', '');
    video.setAttribute('playsinline', '');
    var start = function () {
      var p = video.play();
      if (p && typeof p.catch === 'function') p.catch(function () {});
    };
    start();
    video.addEventListener('loadeddata', start, { once: true });
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) start();
    });
  });
});
