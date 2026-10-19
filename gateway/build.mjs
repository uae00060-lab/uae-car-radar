import {mkdir,copyFile,cp,rm} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('./',import.meta.url));
await rm(root+'dist',{recursive:true,force:true});await mkdir(root+'dist',{recursive:true});
await copyFile(root+'../index.html',root+'dist/index.html');
await cp(root+'../assets',root+'dist/assets',{recursive:true});
