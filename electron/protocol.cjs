const ACTIONS = Object.freeze({install:['-administrador','-apenas-instalar'], repair:['-administrador','-reparar','-apenas-instalar'], diagnose:['-diagnostico'], launch:['-abrir']});
function parseStage(line) {const m = line.match(/ETAPA (\d)\/7 - (.+)/); return m ? {number:Number(m[1]), title:m[2].trim()} : null;}
function safeAction(action) {if (!Object.hasOwn(ACTIONS,action)) throw new Error('Ação desconhecida.'); return [...ACTIONS[action]];}
module.exports={parseStage,safeAction};
