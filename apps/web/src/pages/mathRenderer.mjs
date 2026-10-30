/** @param {string} latex */
export async function renderEquation(latex) {
 const { default:katex }=await import('katex');
 return katex.renderToString(latex,{displayMode:true,throwOnError:false,strict:'ignore',trust:false,output:'htmlAndMathml'});
}
