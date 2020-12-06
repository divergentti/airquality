# Air quality
This repository holds mainly python scripts related to measuring air quality parameters. Measurements may be collected with microcontrollers such as ESP32 or Raspberry PI and passed to the database such as #influxdb via #mqtt #iot and later analyzed with #grafana.

Measuring temperature and moisture may help to adjust HVAC systems so that in other hand energy loss is as low as possible, but also so that microbial growth, like algae and bacteria, do not cause problems.  Saving energy shall be priority from #climatechange point of view.

High concentration of CO2 may cause health issues, but also reduce productivity. Schools do not have plenty of money to spend and therefore inexpensive sensors may be needed. The same applies for households and other locations. 

Measuring dust particles is also important and helps maintaining HVAC systems. Typically filters may be bad quality or they are not cleaned, causing bad and perhaps even dangerous indoor air.

Target is to use inexpensive sensors, which accuracy can be improved either in the python scripts, or in further analysis, with reference values from accredited sources. 

Once system is ready and the data flows to the database, information can be analyzed further and perhaps calculate more intelligent alarms to protect people.

This repository is maintained by Jari Hiltunen, Hanko, Finland. Besides python scripts, most of setups contain also 3D printable cases and drawings. Search them from Thingsverse https://www.thingiverse.com/divergentti/designs

# Ilmanlaatu
Tässä repositoriossa on pääosin ilmanlaatuun liittyviä python-scriptejä. Ilmanlaatuun liittyviä arvoja voidaan kerätä esimerkiksi mikrokontrollereilla kuten ESP32 ja micropython, tai esimerkiksi Raspberry PI:lla. Lähtökohtana on siirtää tiedot mqtt (IoT) avulla Influx-tietokantaan, josta tietoja voidaan analysoida esimerkiksi Grafanalla.

Lämpötilojen ja kosteuden mittaaminen voi auttaa ilmanvaihdon säätämisessä siten, että mahdolliset energiahäviöt jäävät mahdollisimman pieniksi samalla kun mikrobien, kuten homeiden ja bakteereiden kasvu jää mahdollisimman vähäiseksi. Energian säästäminen on ilmastonmuutoksen keskeisimpiä kysymyksiä muutoinkin.

Korkeat hiilidioksidipitoisuudet voivat aiheuttaa terveyshaittojen lisäksi esimerkiksi väsymystä, joka vähentää tuottavuutta. Esimerkiksi kouluilla ei ole käytettävissään paljoa rahaa, jolloin edulliset mutta riittävän luotettavat mittaukset voivat tulla tarpeeseen. Sama pätee toki koteihin ja muihin kohteisiin. 

Pölyhiukkasten mittaus on myös tärkeää, sillä pölyhiukkasten mittauksella voidaan tutkia mm. ilmanvaihtolaitteiston toimintaa ja optimoida esimerkiksi suodattimien vaihtoa tai tutkia mahdollisia pölyn lähteitä.

Järjestelmän tuottaessa riittävän luotettavaa dataa, voidaan sitä analysoida edelleen ja tuottaa näin laskennallisia hälytyksiä ihmisiä suojaamaan.

Tätä repositoriota ylläpitää Jari Hiltunen Hangosta. Sen lisäksi, että olen tehnyt nämä scriptit, olen tehnyt myös  3D-tulostimella tulostettavia koteloita. Näet ne osoitteesta https://www.thingiverse.com/divergentti/designs

