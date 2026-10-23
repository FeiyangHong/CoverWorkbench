from pathlib import Path
import tempfile, sys, json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime/script-test-packages'))
from lupa import LuaRuntime
sys.stdout.reconfigure(encoding='utf-8')
results=[]
with tempfile.TemporaryDirectory(dir=ROOT/'work') as td:
    root=Path(td);(root/'runtime/sv-live').mkdir(parents=True);(root/'data/sv-phrases').mkdir(parents=True);(root/'data/sv-presets').mkdir(parents=True)
    allowed='E:/pilot/working/test.svp'
    (root/'runtime/sv-live/manifest.tsv').write_text('hoshi\t'+allowed.encode().hex(),encoding='utf-8')
    mock='''
    answer={mode=0,id='test',clear=true,lyrics='あ い',phones=false,pitch=false,transpose='0',rhythm=false,modes=false}
    messages={};undo=0;shared=false;path='E:/pilot/working/test.svp';major=2
    g={getUUID=function()return 'group' end}
    ns={}
    for i=1,2 do ns[i]={onset=(i-1)*705600000,duration=705600000,pitch=60+i,lyrics='old'..i,phones='oldphones'}
      local n=ns[i]
      function n:getParent()return g end;function n:getOnset()return self.onset end;function n:getDuration()return self.duration end
      function n:getPitch()return self.pitch end;function n:getLyrics()return self.lyrics end;function n:getPhonemes()return self.phones end
      function n:setPitch(v)self.pitch=v end;function n:setLyrics(v)self.lyrics=v end;function n:setPhonemes(v)self.phones=v end
    end
    voice={paramLoudness=-3,paramTension=.3,paramBreathiness=.1,paramGender=.2,paramToneShift=0,
           vocalModeParams={Soft={pitch=50,timbre=75,pronunciation=80}}}
    applied={}
    r={getTarget=function()return g end,getPitchOffset=function()return 0 end,getVoice=function()return voice end,
       setVoice=function(self,v)applied=v end}
    track={getNumGroups=function()return shared and 2 or 1 end,getGroupReference=function()return r end}
    p={getFileName=function()return path end,getNumTracks=function()return 1 end,getTrack=function()return track end,newUndoRecord=function()undo=undo+1 end}
    selection={getSelectedNotes=function()return ns end,getSelectedGroups=function()return {} end}
    editor={getCurrentGroup=function()return r end,getSelection=function()return selection end}
    SV={getProject=function()return p end,getMainEditor=function()return editor end,
      getHostInfo=function()return {hostVersionNumber=major*65536}end,
      showCustomDialog=function()return {status='Yes',answers=answer}end,
      showMessageBox=function(self,title,msg)messages[#messages+1]=msg end,showOkCancelBox=function()return true end,finish=function()end}
    '''
    def host(script):
        lua=LuaRuntime(unpack_returned_tuples=True);lua.execute(mock)
        source=(ROOT/'integrations/sv'/script).read_text(encoding='utf-8').replace('__CW_ROOT__/',root.as_posix()+'/')
        lua.execute(source);return lua
    lua=host('CWPhraseLyrics.lua');lua.execute("answer.lyrics='あ';main();assert(undo==0 and ns[1].lyrics=='old1');assert(messages[1]:find('入力')==nil)")
    lua.execute("answer.lyrics='あ い';main();assert(undo==1 and ns[1].lyrics=='あ' and ns[2].lyrics=='い' and ns[1].phones=='');assert(ns[1].pitch==61)")
    results.append('Lyrics count mismatch blocked; matching selection updates lyrics in one undo and clears old phonemes')
    lua=host('CWPhraseLyrics.lua');lua.execute("shared=true;main();assert(undo==0 and ns[1].lyrics=='old1')")
    lua=host('CWPhraseLyrics.lua');lua.execute("path='E:/original.svp';main();assert(undo==0 and ns[1].lyrics=='old1')")
    results.append('Original paths and shared note groups rejected without mutations')
    lua=host('CWPhraseReuse.lua');lua.execute("main();answer.mode=1;answer.lyrics=true;answer.pitch=true;answer.transpose='2';ns[1].lyrics='different';main();assert(undo==1 and ns[1].lyrics=='old1' and ns[1].pitch==63);assert(ns[1].onset==0 and ns[1].duration==705600000)")
    lua.execute("ns[2].duration=705600000*2;main();assert(undo==1);answer.rhythm=true;main();assert(undo==2 and ns[2].duration==705600000*2)")
    results.append('Phrase save/apply and transpose; rhythm mismatch blocks, explicit override preserves target timing')
    lua.execute("answer.transpose='127';main();assert(undo==2)")
    lua=host('CWVoicePresets.lua');lua.execute("main();answer.mode=1;main();assert(undo==1 and applied.paramTension==.3 and applied.vocalModeParams==nil);answer.modes=true;main();assert(undo==2 and applied.vocalModeParams.Soft.timbre==75)")
    results.append('Voice preset restores scalar values; voicebank-specific modes opt-in')
    lua.execute("major=1;main();assert(undo==2)")
    results.append('SV major-version mismatch rejected')
    lua.execute("major=2;answer.mode=0;voice.paramTension=.8;main()")
    saved=root/'data/sv-presets/2_test.tsv'
    assert saved.with_suffix('.tsv.bak').exists()
    assert saved.read_bytes()!=saved.with_suffix('.tsv.bak').read_bytes()
    results.append('Overwriting a preset retains the previous data in a backup')
(ROOT/'reports/sv-tools-tests.json').write_text(json.dumps({'passed':True,'scope':'Lua mock host; native validation reported separately','checks':results},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False))
