# Vector_typer
this repository has scripts, this script can autmaticly create Vectors and so much more.

Hi! You’re probably wondering how to use this matrix. First, I need to explain how it works—it’s actually incredibly simple. 
You have a grid of points (for example, 3x3), where the center point represents the "forward" (front-facing) direction. The 
first two rows are oriented downwards, while the fourth and fifth rows are oriented upwards. Similarly, the first two columns 
are oriented to the left, and the fourth and fifth columns are oriented to the right. In practice, you don’t need to draw all 
25 individual sprites; you can just draw 9 of them and then either flip or crop them within your game engine.


BTW, there’s also a script in the folder; if you want something larger—for example, a wider angle—you just need to increase 
the COLS and ROWS values. If you want larger matrices for the frames, simply increase the number for the frame size.


Make By Ete Van A Ńum
