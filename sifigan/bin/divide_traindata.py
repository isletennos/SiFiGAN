train_line = list()
dev_line = list()
eval_line = list()
with open('D:\\GitRepository\\sifigan\\SiFiGAN\\egs\\multi_speaker\\data\\scp\\all.list',encoding='utf-8')as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if i % 10 == 0:
        dev_line.append(line)
    elif (i+1) % 10 == 0:
        eval_line.append(line)
    else:
        train_line.append(line)

with open('D:\\GitRepository\\sifigan\\SiFiGAN\\egs\\multi_speaker\\data\\scp\\train.list', 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(train_line)
with open('D:\\GitRepository\\sifigan\\SiFiGAN\\egs\\multi_speaker\\data\\scp\\dev.list', 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(dev_line)
with open('D:\\GitRepository\\sifigan\\SiFiGAN\\egs\\multi_speaker\\data\\scp\\eval.list', 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(eval_line)

train_line = list()
dev_line = list()
eval_line = list()
with open('D:\\GitRepository\\sifigan\\SiFiGAN\\egs\\multi_speaker\\data\\scp\\all.scp',encoding='utf-8')as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if i % 10 == 0:
        dev_line.append(line)
    elif (i+1) % 10 == 0:
        eval_line.append(line)
    else:
        train_line.append(line)

with open('D:\\GitRepository\\sifigan\\SiFiGAN\\egs\\multi_speaker\\data\\scp\\train.scp', 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(train_line)
with open('D:\\GitRepository\\sifigan\\SiFiGAN\\egs\\multi_speaker\\data\\scp\\dev.scp', 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(dev_line)
with open('D:\\GitRepository\\sifigan\\SiFiGAN\\egs\\multi_speaker\\data\\scp\\eval.scp', 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(eval_line)