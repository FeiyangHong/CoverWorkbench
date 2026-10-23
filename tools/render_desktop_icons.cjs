const CW_ROOT=require('node:path').resolve(__dirname,'..').replace(/\\/g,'/');
const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{const root=CW_ROOT+'/assets/icons',browser=await chromium.launch({headless:true,channel:'msedge'}),page=await browser.newPage({viewport:{width:1024,height:1024},deviceScaleFactor:1});
try{for(const name of ['cw-signature','cw-vocal','cw-studio']){
const svg=fs.readFileSync(root+'/'+name+'.svg','utf8');await page.setContent('<style>html,body{margin:0;background:transparent}svg{display:block;width:1024px;height:1024px}</style>'+svg);await page.screenshot({path:root+'/'+name+'.png',omitBackground:true});
}}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
