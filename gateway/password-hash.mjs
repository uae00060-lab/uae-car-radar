// Run locally; input is hidden and the password never enters shell arguments or files.
import {createInterface} from 'node:readline';
import {pbkdf2Sync,randomBytes} from 'node:crypto';
if(!process.stdin.isTTY) throw new Error('Use an interactive terminal');
const readline=createInterface({input:process.stdin,output:process.stdout});
readline._writeToOutput=()=>{};
process.stdout.write('New owner password (at least 12 characters): ');
readline.question('',password=>{readline.close();process.stdout.write('\n');if(password.length<12) throw new Error('Password is too short');const salt=randomBytes(16);process.stdout.write('600000:'+salt.toString('base64')+':'+pbkdf2Sync(password,salt,600000,32,'sha256').toString('base64')+'\n');});
