#include "gpgpusim_to_graphics_calls.h"
#include "mesa_gpgpusim.h"

extern renderData_t g_renderData;


//called by gpgpusim
bool isDepthTestEnabled() {
    return g_renderData.isDepthTestEnabled();
}

bool isBlendingEnabled() {
    return g_renderData.isBlendingEnabled();
}

void getBlendingMode(unsigned  * src, unsigned  * dst, unsigned* srcAlpha, unsigned * dstAlpha,
        unsigned* eqnRGB, unsigned* eqnAlpha, float * blendColor){
    g_renderData.getBlendingMode(src,  dst,  srcAlpha,  dstAlpha,  eqnRGB, eqnAlpha, blendColor);
}

unsigned readMESABufferWidth() {
    return g_renderData.getScreenWidth();
}

unsigned readMESABufferSize(){
   return g_renderData.getRBSize();
}

//copy the result data to the store object, this store object will be used by the rest of the pipeline in MESA (rasterization and fragment shading)
void writeVertexResult(unsigned threadID, unsigned resAttribID, unsigned attribIndex, float data) {
    g_renderData.writeVertexResult(threadID, resAttribID, attribIndex, data);
}

//get texel size
unsigned getMesaTexelSize(int samplingUnit){
  return g_renderData.getTexelSize(samplingUnit);
}
