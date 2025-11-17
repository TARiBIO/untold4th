from PIL import Image
import os
GAR=os.path.join(os.path.dirname(__file__),"data/garments")
UP=os.path.join(os.path.dirname(__file__),"uploads")

def generate_tryon(user_img,garment,meas):
    u=Image.open(user_img).convert("RGBA")
    g=Image.open(os.path.join(GAR,garment)).convert("RGBA")
    w=int(meas["chest_width_px"])
    g=g.resize((w,int(w*1.2)))
    u.alpha_composite(g,(int((u.width-w)/2),int(u.height*0.2)))
    out=os.path.join(UP,"tryon_"+os.path.basename(user_img))
    u.save(out)
    return out