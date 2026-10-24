"""Fail if a real consumer or enterprise brand appears in code, docs or sample data.

Portfolio rule: every company, merchant and customer in this repo is fictional.
Identity, PAM, IGA and SIEM product names are also blocked: this repo names
categories only.

The blocked names are not stored in plain text. Each entry is kept as two
SHA-256 digests: one of the lowercased term (the lookup key) and one of its
usual spelling (so matching stays case-sensitive and ordinary words are not
flagged). Text is split into letter-only words; every run of 1-3 consecutive
words is hashed and compared against the sets.
To add a term: python scripts/check_brands.py --hash "Some Brand"
Run: python scripts/check_brands.py   (CI runs it on every push)
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess
import sys
from collections.abc import Iterable

MAX_WORDS = 3
WORD = re.compile(r"[^\W\d_]+")  # maximal runs of letters
SKIP = {"scripts/check_brands.py"}
TEXT = re.compile(r"\.(py|md|txt|json|ya?ml|toml|csv|sql|html|ts|js|cfg)$")

TERM_HASHES = frozenset(
    {
        "03f5ed581c44e3cf7672849ca3a6f6bbd3992f988aaf0735fac25d72fc7cacf3",
        "04c2998f3d458c7724f8f3dde10dd431b4f2103e71db8b1e39aa2093f5c32e54",
        "0616a267820d2c788f95dd9d06427dfa90f3b3e776c2687b63a322aa359ee1e6",
        "066b5b5ad80702e14f11863bf5c6e976c2fa01e830f80320905d50fd99f155ed",
        "07863e7a6a2154ba864a71b0818c5ed32f78999430254b2e272d461fcd0d34eb",
        "08bb42a30ca57f3455e11ac74fd30eae1196b25a9e7d634bfc5704d542ab7d20",
        "09a2f4897466c7a542e994bed0ffced8d57e475766c6c3e7d84d2219f567a0d9",
        "0baf38f5da148c7a98b362afba5da1eb781a443f521ed25b049fe34d4ce5edd2",
        "0bf923f90ab2c0c4ae8e0aa463729eef765aa2996309a340dc48759243fb73ac",
        "0e79172671f59f0f867c8ae23afd21d5f44d23f6f019c8328990e53e2c8e3a0d",
        "0f513cc7e925214b50d7a3b01f9c9f622a7b565a12869314528cc32099588b15",
        "0f8ec60dd129da14ddebd1a1a76ec9bf6f6fb9e61f04fb9d52ef21191a5bc086",
        "101e21bef69a3df68f36ca31deb6616f10cc70e4bae8eed9ce83a9effb1fd5cb",
        "1264de97e7d46db15cc30796eeb6138a68431cd581ba51706517c86a65821278",
        "13ed070478ef62c3a7baa36c8d042a9d1cdc0fcbb2af93a795f2ad20ad6e9cb5",
        "14a136223815c492064f143c9673d7b5c8e9ae0f7108eb9bef473cb8078f31bd",
        "1beab50b7ca76bdb802bb385a78cdebe18fc3cfa4b18d5d9ee39a4ba68ecea6a",
        "1cf493e736fae0db2cdb9f0b3b6750ad99d78e2d03db46c65b66da7baaff6913",
        "1d0c5646e860a73fbc3c7cb0fae3c9083657d43544696efe26f790e50c80328c",
        "20abf4bcd62ef27c9b3caa9751670f4c42e187085b757b2e673132c86cedc731",
        "22ffba7a86ea9919593ce4de083c392f0f43149668d89d968da1d70fad195740",
        "24e6654bfd1ab85bebb1f721a4be46e6fdb9ea8974d14442d3aaecd1f971fcbb",
        "2b1da9c840074a3558ef73664428ba21374be164833182f12d90e2372ed89c9e",
        "2b78da3dc866654e6ea7cb2f654df44746b6f02876acbb2a05726ab3d915e47e",
        "2cbb9e58bf3bcbdfe805a2aebb57f84531b114a18e5f0e6377d9f5a7bf86576b",
        "2d140b32b0f822faa25cb3521a0dbb5b2067ddcc2adfbfc81693c6ad5cb59a7e",
        "311ff2d71234e230eb559f843c1f5c548302246a365221713da47017e656e672",
        "33860d208be29fde5630eaa145e2c2e28160e7ad096183c370a7fa2ef6a6c852",
        "38e0c90a73bd834832b7b4ecd6c9a3488d3d6bc46e49ab40c29b60767e502814",
        "3b8eccd79c406969d8fa1a98deea4b0a3d13df5959d6ea421b99222a64055246",
        "3dabb400590f564af9bf8e087de803005f3a5324b0033f4ed43db59aabd403ca",
        "3e808ece8227f5d4fda47690aed90895fc56881b6335d39ace7e8078b240164c",
        "3ee49785593999cef46e1c1482ad1a246d6e319b48149ec2e8cdff05ddf8b236",
        "43250578088ef408762f8c207617cb22bbe6743952a02d65ecc9b2cb21f5b63a",
        "452ddac3092b5a859873096c3e55f0dbffc26c72f7cc9a50a75651ea3f13636a",
        "479d0a486a92e55c156ea1cb76c68c68a92b577fd6b403b7c7484bcecdc3d1f5",
        "4a3892e5bc960fe49946b5f81ed92323657fb35aaaed25f0e65d91ba9187b5aa",
        "4ac6b1d4ae2027e9b9bdce0d15dfabf3ccc8ea20eda2b3f6a8f6be68f772b028",
        "4b1f6f530975ef68d8f30d663efe02fb1e20ca2fdde8c5416ecfeb21fb881e96",
        "4d748ebd71af03a7c325a5ecef86e3768b71597ba3c08dc26624bfdbd84a0a34",
        "4d808f9aa6a8f761c00fe5da41a8528241f2ea593126c641f9c8ca9d5ef1b214",
        "4e8c67d62118bf11a835ab4a0363ffa25e82f1703a4686c03620c6399e7a88ac",
        "4ef9bfe6a5402861fd19b51cdbe76e50ac1cd3cf36e3d20530d57f5dd13ab60e",
        "5344ae4677efc34b108f205590fcd8ba532c31a533bebd15b250ea671bad1fa5",
        "54fa0ac6fb7ba4b0ec2dc9fc8f7d5c553c5c3be6f964e3f6dd49795adda51010",
        "5528a266f145e52b1909113269d53b17369dfa495d541628c661029da13e9237",
        "5ba14c9c0738b2e6450ed1c25f0ad21336f29ee2a4fb83051555a4a6ac6162f1",
        "5dd95c98aff2e783a09348f600def0d5e4e476f71e85e9be91de86aab36544cd",
        "5e9ceb28244d06451ffa713a7552d8d89519875f3db22c7626d04f5379c30710",
        "64026fa7c5b847dd2f4aea394b232b10ed5739e6d422cc6f755101c210e05e99",
        "64686f98a42da48751847c2311865f1588d1d2e3b2575d2cf08b5d5799d2abd0",
        "65819e198c32566ae994e481fd6ab4f725a3c16e916102713a58f22d291aed0b",
        "67933135042afcb5d9b1f95f05e3413ea43559c756a8a666efdd2473c4d25fb3",
        "69d9f7657d4a7ec043cfec0a850137dad26fab1b5bb4bbf3e9182ad667fc0c9d",
        "6c4e02093d91827019c136ebe2d063fecee73cb9e56dcdb96b0a3df52f38682d",
        "6dbe2312a44d0b9025bb3bec029992f9b7f2c00bf8191259fb12c685c9cbaa3b",
        "7105a46cb4c2810f0c916e0bb4b4e4ef834ad42040c471b42c96d356a9fd1b21",
        "712c9df0397999977db3d6223cddf2d8eddce63c1cde2773242f2d805f14cacf",
        "71a5f97944088c9158ad2d0ef23a9bdec9a937e3250afa7580e29d5dc11b5eba",
        "71f566aba763fb7636f03bfeb321c6d4934d4a6d5cb777c49b1c1595260c573b",
        "7358bd4ec877e1b622397ab4f9706b76680348a2886bfc0a675ed0555085d0ea",
        "73f449eb6a3c05d327e23f4442290498a6dc25c5329c8070b24f7f8fb66f333f",
        "743598aceb5d73b958867c51d6387329c3dc447fcecfc2b5983e5616c733b8a0",
        "74c860f63661b29cd747cf485fb26898163066cb84328f3855f877dbbeef5d56",
        "74f8b187fcc4e194881c59f85fde8f03438ecf41ee7db52a93c8d103bd86a0b0",
        "75e49c11a3ae7dc99124de5f000fe42330edfce7c447cd2892d55700f38ade46",
        "7c2dddc2c2580ab843ee18b40ed448ac82ef5a01435e525248b6cea29930da1e",
        "7f3a98bcabcb3fe71d099c69fda6de33a6c0e7b2df8b7dd79ed161f1b0920372",
        "8a72266588ef612e2a307a78d4a903496240406ed2635e18ab918c27e8b60c40",
        "8bd7f200fc6b10abda0cd29a05fac98e97582b7b8976c5df8def7a52e1d4bc8f",
        "8dcd18640a0ac016dc4ec665b42803a3f1cc5d3a9c3f4d3ba65c0096d3b66b6e",
        "91c2e066980410c8864bbfdfb3691aa833453c949399565f2e19912843e8e23b",
        "943c3eeb252dbd176df2295566dad51a65ddc81165de0df9873a4ae9f7bf09bd",
        "9ccfe0b5c67275792b5baa250e5fe58e4d618418b353effc55dd322a59efb9fd",
        "a3145393aa69ec6cabcc651e74ffc989c239d21d9a9ab7b370ccd202b110a983",
        "a38c2d7bfc423b198f0e188e4d988bc1b8e8c107a760f9f66a2fc7e9b5b4ede5",
        "a638e70ffa28c67e202f3197c33ecb343576ede06cef2deeb3dfd9659b7c3002",
        "a77c64b28a40e5179cca9e31e695cd7f7c935e8dc215ab0590eb69ffe48d2efa",
        "a9d21499d1b41fff3759226509c62adf15b698ab086d78cc9726b962389e137b",
        "aae2a2996fca1e1652a705fa6ad57ea2488df4b8158ad3356c7489d888f94eac",
        "ab7d0a36ecbe10c286f92a49bffb57ed6bf5bc6c3a3e15967f3ea8d028316969",
        "ab877737b6081bd1adaf7cae0f5d18f34c5a8523e399bd672e0f80de2b95a502",
        "afe4d16f403a383f07814bbe04a5e7c5a7dc62ba5ce4040fc85514c29e0e88ae",
        "b0126946c556dc47a63edd3ba7ab3671ef0a46c22d51775debc63291b510fccc",
        "b023b39c07dc15a7f8aa898016a1cb8eda735384b8a59fbfe3a35114260c929e",
        "b1f7021cb83ba1b23f08e848a0df023bb849e79e112661ed05b9df2719013eeb",
        "b21492b15d85500ef49e5ad990ec8a530c27772b9a3d129770fd6c733257c19b",
        "b91bf0e0084fb93f9f8ea08bf575332a011a30700abb33235f7ade44955eceaa",
        "b922b7e0ba4cfdb9d843570dfde0af429181655f71f76fb45ffc923f074adfbc",
        "c3b598d75fe2d28502c175c76c44c3cf22bf9645030835699a3677829c493efa",
        "c6816dc95102dc4860508c8f025f8fcef4fa01996ab8ab39ff51e03630f1bdcf",
        "cafaad8980a6f6b0d22ebca81b8f1705caf925ec150c96c3c17cd6a514d4f217",
        "cbc62794911ff31b2864ecd3dbbbee7ebcb7ea41c5a42e2cba377f3cfdb42811",
        "ce409c401c60f34c14e415dd6174390af9c72564209e25db800eaf5f7a473670",
        "ce749e840dcada0f9196edd49327ae5b3ab16f1d0405e72c1cb7d62b04538a42",
        "d1c7c99c6e2e7b311f51dd9d19161a5832625fb21f35131fba6da62513f0c099",
        "d1d760dba0da539cc4f9d3dc25966cecc3c785aff7a23298c7057028b8c5e1df",
        "d4994cbb1fe992ec5b17b9e18fb2e871801b90f734d8157beac461ea0b4498e5",
        "d515d8e80615e3ba993f9a4878132bb7ec1ae275b86d4bb9ef6dd8b3431e7a5a",
        "d9082bdcf7eaf584e640203ff313a74a401cab4bc2167979eedc76a0019c0334",
        "e357fc9a6a65dc31d1620d2e68e5c9da2cb2e829b7c413eb49850967461443f4",
        "e5f2f4ada0333086bcc638d7a9326b77bf5cf9b42fb402001734639f860fa53b",
        "e759968ca9278b8dde9f515ff1957813343dc35dbd2e5f68b38b5a17e29fe541",
        "eb91bc5d3360a9fc324ddb37f845e47ec4180723a236b96dec75a3a0813383a7",
        "f342fc42b447003b7e736e1a3f154d99c1ca6a2e44bbc47b507969ddd1a27455",
        "fdd823e31be438f6ab80b00191ae7725a78568c954254f32ed1d7b0a8b509e7f",
        "fedb24c98f783a5d22564ae15c2ed2edcf6cc7e4e90f398414744e683f5d2629",
    }
)

SPELLING_HASHES = frozenset(
    {
        "04ace81129308b95f284d1960ac959c718cf1506f5e915d20970e16798d31ae0",
        "06fec48a171515f60ea99fdd762d76fe790fd90b424e7149c7416e6b8ebb5923",
        "0760d36d82f6c5ec7490021b0903b78a97c6c914d56bd681dc1814396c9472e6",
        "07d1df59206ae1888ade8a5957387d7c496e2a4685cca1c5a55482b23b7eb0d1",
        "09f41fd7f49962b44a2d86951147c3db7e5030357de98a2f78ce5a51dd92b979",
        "109475e81527f5088ad70e3d2accb9e30fda546d9c12bf9b8cd802e335fa47a1",
        "10c2fec550e262efcc23279e9737cc8a9d33f065d1c5360c1db7c89130a61988",
        "1337222d995bf50cdb9fe038b705c9e23adc8fb4975308b8559f228c5b517257",
        "153091ce6e774499ac663ffcc9849da5880059b1e3ba334344fb4be7102c5556",
        "1567ed22cfc0030edaac5f2b28a84b12f3932160e4748724b98a2b2b7016d227",
        "15b201796837385fb129c2cede3326a4c0a8d07c20283b6f3cade16b116dc124",
        "182503d30242e06bde3d04cd601c4264bc1835a68263230fdb4a04ad2a49fdb9",
        "1a34654a0c199abf24094217754c9289c77d6bc8174a5533a39733dc4daa51b4",
        "1d927621f5321e9910c44da076ab76efb3de58b81344f5461544d8fa12f42318",
        "20a37477a6c3e645d957e75c51886f7622fd06d68a6121cde0b0ccd731b95dfd",
        "26363a5cca19307788d153c577b56142fe54c51e20b6baa2b6c2926dc0dacf0e",
        "2a221fa7abe9b2677c451bbbc35638f40e77031d1f0cb7cc2079a601d6bc9f88",
        "2e5576f58d325a4a502ea6f9b6a659eb68a2e8b521a49d0400c9ce0fe7001d20",
        "34bcf900ceb1aca5f87573ab6c528c25c3320571426c0724e7d52a1efd1ca071",
        "34f9d133670893cb80dd054fd643e888adb5fdce82b27cf9b8a239ea4c32403d",
        "3746c531f6062ac4fa1602185b8841d88ff132446ae8f2d4088a4d93b8679558",
        "37dbbb7c3558682df1334e47875e8d7d210057614dce1cb48f65c27d460c088f",
        "3acc59af16d7968b5b8eb8b2b226cb0d81a3714216d82308bab699757ac569d8",
        "3cfbdbc3ba7620f9b1c62606674335fba55a6eb7d7d68ef69d6720f5d2870ff6",
        "3eab285c90aa322352c76758fdb214af326503cf5eaeca3ee203e7b7cbb64f1e",
        "3ffd81f600c0fa9482726112f9d3c9ae031fdd82d7adf228c37df1a997359149",
        "4150177b54900ee886f6f1ce42adeb5c116875e07ec181df3d989e0475f01aee",
        "49d2dc07acd9eff540ded01867adfbcbc4139f5fd7cb0eed6c717edb10ffa8fd",
        "5257f809148be0dffe138f353cddf0b82bd2bc346ef8cfbf1500d1b570229d74",
        "571ce0217afc888b726c48586abd561fe965b5e6c8677d8c24b037e6308ca4af",
        "594ae4e99a84b96dcfc9d46736354dda12b1bcedab0708de6a8087ae5919e7d8",
        "595ef7033083d7fd9dd4903ca423eaaae492203d1a194c62d1f585182c31a719",
        "597d0dd6aa15b00d9be09a8f5eb48649e84e12a3c9b671f50efa210e7ff0cbe5",
        "5b945079589d1d08072cd062a9fb03d5774e2be828f3bbbf663de10f5b200864",
        "5dfec4958bfdf2f0c41409de97176deced4c0456dbb1b174853cbe19515625ee",
        "5e875bc90a3601477b5edf4d7640cbf77483971b3735facb115b3125add68c49",
        "5f87ca22d67c6ff661d2839e68130d17b4e764de68ece4c5d14b4e127d85fbfe",
        "60b103692bd44efe9b0174d16df4462d9ad1cfe2b778dc10367868d44f2d97eb",
        "6429bf3f04bbe72937003b891e38621ba9d00e3fde2907615a005c0e2381acef",
        "66519047f57335516bcd37b9dab2d47e3fab614e457fced3914af0617f55feab",
        "67ecc65d314dc609d01f282c9c49c2164eefd19e252f27e85c72962fe27648ea",
        "681e732cd116f5b1b9e134f2fe3b712aaa37b0c2237e4f0d7dc8d97714817a9e",
        "6a650889405412f73844a643e3ee0c4d4ae4ad3489e1f1862244cbc2d61b93f7",
        "6c5684eced5c1869d7838fd59e32d07ebcb1b4a277bb7878227b97ab6cdc5e28",
        "6cd9e83c5d4ca255a28be2693174b3be40aa6f76bb645bd75bb505cb485e12e8",
        "6ff3bf046e4a00674acc30cd8e837481dbd4c55308e66e563001c6a3f967b8a3",
        "7005c0064bda4edb7ad7d500cb081ee70425ba64442759ca3562a6578f19abe6",
        "7006a191ba3a4a863abbe7db05c1a21e476a71bf7cd234df0abe43f06f348d62",
        "7223f950e0e91ffd8c5d06e6021c7e868ecba887a1f4a88ba5a37144ccd1b8db",
        "746741aebf5cb0eb3620ea6f35ecc176e8b8304acfc18770b2819a9da1304706",
        "77a5cca5e68a26f8aff056d7cab556fc04e8ee79ed3436e378129a0f7d6239ff",
        "7b1f660dabe3be9ee163bd0fa61302164c6a5282aec0a570c31f070c402aa18c",
        "7b3497a09659299d83703211dfa0476b34467bf772b312e39296ff289f61e3b8",
        "7c68dcb63c2a534f7f9318466f4498f404a5519400cc4170cf43aef1975db817",
        "7c7393f9939e6c1c46878d7c3c3b3797e35bbfb30382d58ecebde667a5cf586d",
        "7fbfb81fc52dfefef50aca038126abcd46505b3fb5672daa3e473558e507eb48",
        "820763ae11ab34ea1158eade919f9fc3d96d0217f1cc1c1aad98cc204ebc11bd",
        "84be93d567336703dd0ce8906a89707ca3673c3fa74825c4f8b33cbb8b76ca26",
        "872658f70bc1400203ca7609283c848f8e4100135a30993a6cabd4e093c8c490",
        "88470a2affa82c8a9b801f69dc76b757a236db1af1fb474befbb26a75f89151c",
        "8c3c4342634de60cfbeee646f4f93774002d475ead5d1e5f41cf49b625cd0e74",
        "8dd7943982acc692fef67056acf8c62c4b742abff6a17e7ea428bea27da66720",
        "8de070b69bc9839dcc88f27fac55fc34bde02bd4ebf0ed5a45b001f49dd6c5a0",
        "8e7969004a424e5006107e0f6ae8f0af15b7587721a8144c68c987f94b379f46",
        "922fd1ec8a1bde5fe65ca44b0160b9c4bdb3746ba1f104014e6b347ae4703f18",
        "94a05775d9f11c526a340b3421e2f6a959ecaeacbed31659a2d3153c14603483",
        "94cbedc10bf32c2ec7759a9003223b56d3b48cc95ab0235c1b484610807a2911",
        "952395274255063a41aebea974555f153e354ebeb6d30a49150d428d50dd0a89",
        "977ad75fc9acd67a07bd5f002ae330a11501e11b4fcbeb0836f7a8ae099fc810",
        "9890be5d552705917edaab50f44424601d158a133a4daf23ca90a99dc691ba47",
        "9bb3a91fbff870b3200bfaef265068482e94e3f63b3db7091de01ae126813177",
        "9bfb94f11c9b617fb14a2452f0e243759147ef9eb8bf60d7121787d4504eafa4",
        "a1069ec9b334eaa4252f2da70f2fc4103bdffd9f8765d1614bf9f0b9e5e351d4",
        "a1593ecc5a13b7a066c20b6c85dd945ba178a9618c95d50bbe52e4a834b5082d",
        "a1c651b3754e83a8c20ec14c611eed9eacd6b777a0551cb783c9eb417b35803a",
        "a305f0b8cb1ccd856cf68795a463a17b3aa56198bf5c464dc8c8094c340bc06a",
        "a725bda1f33e4ca05e39bfd5a373d20cb535ce9d060fbebefa2aa010ba224cd0",
        "a9fbeb9d17ec60d65480c4c63d01866ef99de5cb9d6b0993ae2160fd8c7394eb",
        "ab1685351b77d8628ab714cbf5d4e4c27b5ecb9a4d34ecc2c2c80b6081da4a23",
        "ab43fc6eec59a19cdda24d2d5fe1d523c5c2a0cb329912ac659ac2856bb08d67",
        "ab8a4f6bb84d161b3622afe130be97ddfa367e1b8707e49e5437a0b87ba1ae55",
        "ae4fc6a15d1ce96b689ebf731847ea100a43306171f2d4db23f01a2051f599b9",
        "aed2ad7e28c8a52ca5b9537b14dd9441405c2750522a2ea166695a6465d54364",
        "b2a940b2a2ea3fe619e319d852a5260a74caccf5d86ade22d2a29ca327689ee1",
        "b31c19fc35cbddf352b48af8a8f50336aac49d8a09aef83e0ce8431b1f825408",
        "b68bdf234dc478a2ac78e71d7b77a8e979a54004afb22a3d357c3f06b774dbe8",
        "b756e6b19c71172a9e98d3d209d4f9e84e4692fc150c6dfc9686652a0b27603b",
        "be433280de3a43652ed7b4e6b8a1f3bf211f3fdb51e19b204a1c5274b2093cbd",
        "c27b11079ad00b2842ff96fb4d50463cb3aff4035f168fa08a052d191f41dae1",
        "cb4f508e5fbafedcacac2c71f7ab5992e70feb21d86e5aaed62253eb6e823785",
        "cd5b7b9fb7b9cbb140de33c39af7cb8e843f27e4eb3ec3a43d12d94a7e99db5f",
        "cf3da28f9bb8fc89df61256640a1255342f814ead6b727831481ee5b186d1b7f",
        "cf7acf0487c872cc40d813e389b991dfb2b56069867109bc8dede1f3d1eabcec",
        "cfe1ae6e7f3ac8a6d5fc112467005bacd3f469ec2dd42a2bb0d54f9b797ab65c",
        "dd9e85b8b5cba698c190d49342ce0eeb0f5788862c64704025733509d74b40dd",
        "de5e065334fc2ea166567d3643e4c9eff01cf49cdb9d571a6e8621ea3fafd557",
        "e2c258181616411eb4965c54169d0351e0f0bf4e74d75f55dbe91f26c1447aa0",
        "e7ccb35263c6b8a0fc2f2d69c735f57a66d25ce7fe23d212c1bccbed98e22435",
        "e8ee962ed9368262aec313560c392f998152b3be7f89d6db6c8e8ed223122e9e",
        "eb46c4263e566890ac41b23924b12fe0371ae76eaf769b88fd2c86600622bbbe",
        "ef969f1c568f2789fdffb97da0da7c138039029adade51f60f13708bf43d1c3d",
        "f09f149fa26808f8702a6de3f1df63cc9e4651987f3109ee81002207f1477b6d",
        "f30ed7c8e6d52d68f4d4e3fe81e7a48e3f36af156c1dd0012d64d3e8b540a4c6",
        "f3dce2762403f100f5ecacd0df3360ce583fc3d438f0e3c4377ba60fc0918624",
        "f3f5cc986b466b373e36cd7ae0091abe13bcbb26b6fd79e520a66d7e2ef3758c",
        "f3f5d1d9aba493153151e468915ca995a3355692da5ddc823e42044333a9deff",
        "f5ab6a5b89c7f8e8548f0921ab95e6973847743ef5b959bb5678357a972f2226",
        "f5b4b42712a5c76e1294bbb874e6f6e30edfbc4c63eee3b3cfd913bac1ad03a8",
        "f62822f07f4b92952bf331bc74d4c2b01466555d4c9403e914bad210fd8e88b5",
        "f89f85382f9c9bd30a092bba46a65e04a9fa43d43d08c90eb42c6a15182c0443",
        "f92d73d6ab3297b563b9c35cfe29b1f1f43cf7c94d1adecfd2b2f62a61dfc809",
        "fad070cff2ed8a64d61440ab5e3c447beb77543f53fa331a1effd23f441e2768",
        "fb7accfff8c6f8ea9b03c91ee5576d0d08080e9ba35918d801aaeb6020dbc88c",
        "fe78c4893082721032c30fc94a95f9ed0ac6d2ff258117ae4c05aa2adac1ffe3",
    }
)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def find_hits(line: str, term_hashes: Iterable[str] = TERM_HASHES, spelling_hashes: Iterable[str] = SPELLING_HASHES) -> list[str]:
    """Return blocked names found in one line, left to right, non-overlapping."""
    terms, spellings = set(term_hashes), set(spelling_hashes)
    words = list(WORD.finditer(line))
    hits, i = [], 0
    while i < len(words):
        for n in range(min(MAX_WORDS, len(words) - i), 0, -1):
            candidate = line[words[i].start() : words[i + n - 1].end()]
            if digest(candidate.lower()) in terms and digest(candidate) in spellings:
                hits.append(candidate)
                i += n
                break
        else:
            i += 1
    return hits


def scan(root: pathlib.Path, files: Iterable[str], **hashes: Iterable[str]) -> list[str]:
    out = []
    for f in files:
        if f in SKIP or not TEXT.search(f):
            continue
        for n, line in enumerate((root / f).read_text(errors="ignore").splitlines(), 1):
            out.extend(f"{f}:{n}: {hit}" for hit in find_hits(line, **hashes))
    return out


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "--hash":
        print(f"term:     {digest(argv[2].lower())}\nspelling: {digest(argv[2])}")
        return 0
    root = pathlib.Path(__file__).resolve().parent.parent
    files = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard"], capture_output=True, text=True, check=True
    ).stdout.split()
    hits = scan(root, files)
    if hits:
        print("Real brand names found (use fictional names instead):")
        print("\n".join(f"  {h}" for h in hits))
        return 1
    print(f"No real brand names in {len(files)} tracked files.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
