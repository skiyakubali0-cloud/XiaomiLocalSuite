package local.xuanyuan.unified;

import android.graphics.*;
import android.graphics.drawable.Drawable;

/** Small line icons drawn at device resolution; no image assets or dependencies. */
final class UiIcon extends Drawable {
    private final Paint p=new Paint(3);
    private final int kind,color,fill,size;
    private int alpha=255;
    UiIcon(int kind,int color,int fill,int size){this.kind=kind;this.color=color;this.fill=fill;this.size=size;setBounds(0,0,size,size);}
    @Override public void draw(Canvas canvas){
        canvas.save();canvas.translate(getBounds().left,getBounds().top);canvas.scale(getBounds().width()/40f,getBounds().height()/40f);
        p.setStyle(Paint.Style.FILL);p.setColor(fill);p.setAlpha((fill>>>24)*alpha/255);canvas.drawRoundRect(0,0,40,40,12,12,p);
        canvas.translate(8,8);p.setStyle(Paint.Style.STROKE);p.setColor(color);p.setAlpha(alpha);p.setStrokeWidth(1.65f);p.setStrokeCap(Paint.Cap.ROUND);p.setStrokeJoin(Paint.Join.ROUND);
        switch(kind){
            case 1:canvas.drawRoundRect(6,2,18,22,3,3,p);canvas.drawLine(10,18.5f,14,18.5f,p);break;
            case 2:
                canvas.drawLine(3,9,3,4,p);canvas.drawLine(3,4,8,4,p);canvas.drawLine(16,4,21,4,p);canvas.drawLine(21,4,21,9,p);canvas.drawLine(21,15,21,20,p);canvas.drawLine(21,20,16,20,p);canvas.drawLine(8,20,3,20,p);canvas.drawLine(3,20,3,15,p);
                Path star=new Path();star.moveTo(12,7);star.lineTo(13.5f,10.5f);star.lineTo(17,12);star.lineTo(13.5f,13.5f);star.lineTo(12,17);star.lineTo(10.5f,13.5f);star.lineTo(7,12);star.lineTo(10.5f,10.5f);star.close();canvas.drawPath(star,p);break;
            case 3:canvas.drawCircle(12,9,5.5f,p);canvas.drawLine(9,14,9,18,p);canvas.drawLine(15,14,15,18,p);canvas.drawLine(9,18,15,18,p);canvas.drawLine(10,21,14,21,p);canvas.drawLine(12,0,12,1,p);break;
            case 4:Path shield=new Path();shield.moveTo(12,2);shield.lineTo(20,5);shield.lineTo(19,13);shield.quadTo(18,18,12,22);shield.quadTo(6,18,5,13);shield.lineTo(4,5);shield.close();canvas.drawPath(shield,p);canvas.drawLine(12,7,12,13,p);canvas.drawPoint(12,17,p);break;
            case 5:canvas.drawRoundRect(3,5,21,22,3,3,p);canvas.drawLine(3,10,21,10,p);canvas.drawLine(8,2,8,7,p);canvas.drawLine(16,2,16,7,p);canvas.drawLine(8,15,10,17,p);canvas.drawLine(10,17,16,13,p);break;
            case 6:Path bell=new Path();bell.moveTo(4,18);bell.lineTo(6,14);bell.lineTo(6,9);bell.cubicTo(6,1,18,1,18,9);bell.lineTo(18,14);bell.lineTo(20,18);bell.close();canvas.drawPath(bell,p);canvas.drawArc(9,18,15,23,0,180,false,p);break;
            default:for(int x=0;x<2;x++)for(int y=0;y<2;y++)canvas.drawRoundRect(3+x*11,3+y*11,10+x*11,10+y*11,2,2,p);
        }
        canvas.restore();
    }
    @Override public int getIntrinsicWidth(){return size;}
    @Override public int getIntrinsicHeight(){return size;}
    @Override public void setAlpha(int value){alpha=value;invalidateSelf();}
    @Override public void setColorFilter(ColorFilter filter){p.setColorFilter(filter);invalidateSelf();}
    @Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
}
