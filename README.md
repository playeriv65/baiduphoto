# pybaiduphoto

## Maintained inspection tools

This checkout adds a metadata-only CLI while retaining the original Python API.
Use Python 3.10+ and [uv](https://docs.astral.sh/uv/):

```powershell
uv sync
uv run baiduphoto doctor
uv run baiduphoto list --kind Album --limit 20
uv run baiduphoto list --album-id ALBUM_ID --limit 20
uv run baiduphoto inventory --output .local/inventory.jsonl
uv run baiduphoto inventory --album-id ALBUM_ID --output .local/album.jsonl
uv run baiduphoto plan --inventory .local/inventory.jsonl --output .local/plan.jsonl --destination D:/photo-backup
uv run baiduphoto plan --inventory .local/inventory.jsonl --output .local/videos.jsonl --destination D:/photo-backup --media video
```

Run from the repository directory. Save cookies from your own authenticated
`https://photo.baidu.com` session in `.local/cookies.json`. Supported formats are
an array of browser/CDP cookies (preferred, preserving domain/path/security) or
a JSON object mapping cookie names to values. Automatic browser database
decryption is intentionally not required; modern Chrome encryption can prevent
older `browser_cookie3` workflows from working. Refresh this local file when
the session expires. Cookies and exports are private and ignored by Git.

`--cookies PATH` and `--config PATH` are global options placed before the
subcommand. `BAIDUPHOTO_CONFIG` can also point to a JSON configuration file.
See `config.example.json` and `pybaiduphoto/defaults.json`. Do not put secrets
in either committed file. CLI output is UTF-8 JSON; progress goes to stderr.

`doctor` tests all five list types, the second media page, first-page album
contents, single-file link resolution and ZIP link resolution. Resolving a
link does not request its media payload. A successful check does not establish
that the eventual CDN transfer, original-quality preservation or checksum
verification will succeed. Upload, delete, rename, import and download payload
operations are not exercised by this CLI.

`inventory` follows cursors, deduplicates file IDs and fails on stalled cursors.
It writes JSON Lines containing IDs, filenames, checksums, byte sizes and times;
signed URLs, face/location metadata and cookies are excluded. A failed export
keeps a `.partial` file, and only a successful scan produces the requested final
filename. Existing outputs are not overwritten. A scan describes the library
while it is being read, not an atomic snapshot if another device changes it.

`plan` runs entirely offline. It supports filename substring and photo/video
filters, calculates total bytes and assigns Windows-safe paths with an ID prefix
to avoid duplicate-name collisions. It creates the plan only; it does not create
the media destination or transfer files. Keep inventories and plans in `.local/`.

All CLI network commands construct `API(..., read_only=True)`. The transport
allows only known inspection endpoints (including the album listing POST) and
blocks media URLs and cloud mutations before a request. The original library
keeps `read_only=False` for compatibility. Callers can explicitly opt in:

```python
from pybaiduphoto import API
from pybaiduphoto.cli import load_cookies

api = API(load_cookies('.local/cookies.json'), read_only=True)
page = api.get_self_1page('Item')
url = page['items'][0].get_download_link()  # Metadata only; signed URL is private.
```

HTTP requests have bounded timeouts, explicit HTTP/API errors and token parsing
independent of template field order. API cookies/tokens are not forwarded to
external media hosts. Legacy upload/download/mutation functions remain available
through the library, but are outside the verified read-only workflow.

Validation:

```powershell
uv run pytest -q
uv run ruff check pybaiduphoto/API.py pybaiduphoto/General.py pybaiduphoto/OnlineItem.py pybaiduphoto/Requests.py pybaiduphoto/cli.py pybaiduphoto/config.py pybaiduphoto/pagination.py pybaiduphoto/planning.py tests
uv build
```

## Original API documentation
一刻相册 API


# 安装
```
pip install pybaiduphoto
```

# 初始化api

```
from pybaiduphoto import API
api = API(cookies=cookies)
```
其中`cookies` 从网页中抠取，如下:
```
cookies = {
            'BAIDUID': 'F...',
            '__yjs_duid': '1...',
            'BIDUPSID': 'FD...',
            'BDUSS_BFESS': 'lRLNl...',
            'STOKEN': 'be2...',
            ...
        }
```
方便起见，也可以通过`browser_cookie3`(注意自己pip安装一下)直接从浏览器中抽取cookies(注意先登陆)，以chrome为例:
```
from pybaiduphoto import API
import browser_cookie3

api = API(cookies = browser_cookie3.chrome() )
```


# 获取对象

## 数据对象
数据对象是指图片或者视频。首先要得到对象的列表信息。因为量比较大，所以信息是分页的。获取第一页的方式如下:
```
list1 = api.get_self_1page(typeName='Item')
```
其返回值包含以下内容：
```
list1.keys()
>>
dict_keys(['items', 'has_more', 'cursor'])
```
`items` 是该分页中的对象集合，是一个list。可以直接通过`.info`查看对象的信息:
```
L=list1["items"]
L[0].info

>>
{'fsid': 63.....,
 'path': '.....',
 'md5': '49dda......',
  ...
 'collect_status': 0}
```
友情提示：为保持良好的OOP代码结构，不推荐直接使用`L[0].info`，内容可能会变化。

对象可以直接下载到本地目录:
```
L=list1["items"]
L[0].download(DirPath='/Users/XXXX/Desktop')
```
通过`has_more`来判断该页面是否为最后一页。如果不是最后一页，下一页的获得方式为:
```
if list1['has_more']:
    cursor_nextpage = list1['cursor']
    list2 = api.get_self_1page(typeName='Item',cursor=cursor_nextpage)
```
可以删除:
```
L[0].delete()
```

high level函数`get_self_All(typeName='Item',max=-1)`是对`get_self_1page`的一个包装，用于获取所有对象。`max`设定最大获取数量，`max<=0`对应获取全部。例如(注意，内容多的话可能有点慢):
```
L = api.get_self_All(typeName='Item')
```
则`L[0]`直接就是一个数据对象。



## 相册对象
```
list1 = api.get_self_1page(typeName='Album')
list1.keys()
>>
dict_keys(['items', 'has_more', 'cursor'])
```
其中`has_more`, `cursor`意义同上。items中的对象是`相册对象`。可以用过`append`将图片添加到相册。例如: 将最后一张照片添加到第一个相册:
```
ilist = api.get_self_1page(typeName='Item')
alist = api.get_self_1page(typeName='Album')  
a = alist['items'][0]
a.append( ilist['items'][0]  )
```
也可以添加多个对象，`a.append( ilist['items'][0:3]  )`

可以删除该相册:`a.delete()`,默认会删除相册中的子内容。如果只删除相册但是保留子内容，可使用: `a.delete(isWithItems=False)`

获得相册中的对应数据的方法是:
```
res = a.get_sub_1page()
```
返回相册中对应的数据对象。返回内容的key为`dict_keys(['items', 'has_more', 'cursor'])`。用法同`get_self_1page()`。同时也存在函数`a.get_sub_All(max=-1)`

获取相册的名字或者ID:
```
a.getName()
a.getID()
```

重命名:
```
a.rename(newName)
```

设置公告:  
```
a.setNotice("balabala...")
```

## 人物相册
用法参考上面的相册对象，只是把`typeName`设置成`Person`。例如获得所有的人物相册的方式：
```
pList = api.get_self_All(typeName='Person')
```
该对象类似与相册对象，不过是百度自动按照人脸分类了。函数类似的还有`get_sub_1page`和`get_sub_All`，用法同上。

## 地点相册
用法同上，设置`typeName='Location'`

## 事物相册
用法同上，设置`typeName='Thing'`


# API 操作

## 上传文件

```
api.upload_1file(filePath='/Users/XXXX/Desktop/test.png')
```

若要上传到指定相册

```
api.upload_1file(filePath='/Users/XXXX/Desktop/test.png', album=a)
```
其中`a`是获取相册列表得到的相册，例如`a=api.get_self_1page(typeName='Album')['items'][0]`。

## 创建相册
创建一个名字为`test`的相册：
```
a = api.createNewAlbum(Name='test')
```
返回的是相册对象（见上面解释）。!!!注意，可以创建名字相同的相册。另外，此处后台来看会用到一个`tid`的信息，来唯一标识一个相册。我不知道这个是怎么生成的，目前用一个18位的随机数来代替测试可行。但这带来一个未来失效的风险。有聪明的同学可以帮我研究研究这个`tid`从哪里来的。

## 搜索相册
根据关键词搜索满足条件的相册。
```
aList = api.albumSearch(keyword="xxxx"，limit=30,start=0)
```
返回值包含`aList.keys()`->`dict_keys(['items', 'has_more'])`. 所有满足条件的相册对象包含在`aList['items']`中。因为这是一个新增加的功能，所以官方应该是内部做了什么标记。很早之前创建的相册搜不到，网页版的也搜索不到，没办法解决。



## 网络代理
在初始化对象的时候加入`proxies`字段,例如
`api = API(cookies = browser_cookie3.chrome() , proxies = {"https":"socks5://127.0.0.1:1080"} )`。`proxies`的格式同`requests`库需求一致。

## 批量下载
通过`url = api.get_batchDownloadLink(items,zipname=None)`可以获得一个下载地址，复制到浏览器回车可以下载一个zip包。这其中`items`是一个标准的Python list,内容是`数据对象`。注意如果要用参数`zipname`的话，后缀名要加上`.zip`，不然报错。

## 从百度网盘导入

例子:

```
api.importFromPanDisk(dirPath="/anime")
```

其中`anime`是百度网盘中的一个文件夹。也可以是更长的路径如`dirPath="/path1/path2/path3"`。该函数本身没有延迟，但是调用完成后需要等待一刻相册后端慢慢传输数据完成。另外官方说了，从网盘导入目前只支持文件夹。




# Contribution requests
- ~~批量下载，遇到一些困难，有js比较好的同学可以去[issue](https://github.com/HengyueLi/baiduphoto/issues/4)帮着看看。~~(感谢@foxxorcat)



# 总结
虽然只在mac上测试了一下，但是应该其他系统也能用。大致看起来能跑通，基本功能可以实现。有各种问题的话再慢慢研究修复。

# 免责申明
此脚本（API）仅供学习交流，禁止商业使用。使用软件过程中，发生意外造成的损失由使用者承担。您必须在下载后的24小时内从计算机或其他各种设备中完全删除本项目所有内容。您使用或者复制了以上的任何内容，则视为已接受此声明，请仔细阅读。
