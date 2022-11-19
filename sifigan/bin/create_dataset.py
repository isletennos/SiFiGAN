import glob
import os

dirs = glob.glob("D:\GitRepository\sifigan\SiFiGAN\egs\multi_speaker\data\wav/*")
lines = list()
for i, dir_ in enumerate(dirs):
    files = glob.glob(dir_ + "/*")
    for file_ in files:
        line = "data/wav/{}/{}|{}\n".format(os.path.basename(dir_), os.path.basename(file_), str(i))
        print(line)
        lines.append(line)

with open('D:\\GitRepository\\sifigan\\SiFiGAN\\egs\\multi_speaker\\data\\scp\\all.scp', 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(lines)