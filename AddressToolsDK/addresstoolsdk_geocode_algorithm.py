
# -*- coding: utf-8 -*-

"""
/***************************************************************************
 DkAddressTools
                                 A QGIS plugin
 This plugin provides tools to work with Danish addresses within the QGIS processing framework
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2019-09-06
        copyright            : (C) 2019 by Septima
        email                : asger@septima.dk
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = 'Septima'
__date__ = '2019-09-06'
__copyright__ = '(C) 2019 by Septima'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import json
from qgis.PyQt.QtCore import QCoreApplication, QUrl, QVariant
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import (Qgis,
                       QgsProcessing,
                       QgsCoordinateReferenceSystem,
                       QgsExpression,
                       QgsExpressionContextUtils,
                       QgsFeature, 
                       QgsGeometry, 
                       QgsPoint, 
                       QgsField,
                       QgsFeatureSink,
                       QgsMessageLog,
                       QgsNetworkAccessManager,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterExpression,
                       QgsProcessingParameterFeatureSink,
                       QgsWkbTypes,
                       QgsProcessingFeedback)

#from processing.core.ProcessingLog import ProcessingLog




class DawaGeocoder():
    DAWA_ENDPOINT = "https://dawa.aws.dk"
    DAWA_ADDRESS_TYPES = ["adresser", "adgangsadresser"]

    def __init__(self, address_type):
        self.address_type = address_type

    def wash_uri(self, address):
        trimmed = address.strip() if address else None
        if not trimmed:
            return None            
        return f"{self.DAWA_ENDPOINT}/datavask/{self.address_type}?betegnelse={trimmed}"

    def address_uri(self, id):
        return f"{self.DAWA_ENDPOINT}/{self.address_type}/{id}?medtagnedlagte=true"

    def wash(self, address):
        url = self.wash_uri(address)
        if not url:
            return None
        request = QNetworkRequest(QUrl(url))
        reply = QgsNetworkAccessManager.blockingGet(request)
        return json.loads(str(reply.content().data(), encoding="utf-8"))
    
    def address_from_id(self, id):
        url = self.address_uri(id)
        # QgsMessageLog.logMessage(f"URL for id [{id}]: {url}",'Geokoder', Qgis.Info)
        if not url:
            return None
        request = QNetworkRequest(QUrl(url))
        reply = QgsNetworkAccessManager.blockingGet(request)
        return json.loads(str(reply.content().data(), encoding="utf-8"))

    def geocode(self, address):
        washed = self.wash(address)
        if not washed:
            return None
        cat = washed["kategori"]
        id = washed["resultater"][0]["aktueladresse"]["id"]
        dawa_addr = self.address_from_id(id)
        denotation = dawa_addr["adressebetegnelse"]
        adg_adr = dawa_addr if self.address_type == "adgangsadresser" else dawa_addr["adgangsadresse"]
        coords = adg_adr["adgangspunkt"]["koordinater"]
        point = QgsPoint(float(coords[0]), float(coords[1]))
        return {
                    "id": id, 
                    "category": cat, 
                    "denotation": denotation,
                    "accesspoint": point
                }



class DkGeokoderAlgorithm(QgsProcessingAlgorithm):
    """
    This is an example algorithm that takes a vector layer and
    creates a new identical one.

    It is meant to be used as an example of how to create your own
    algorithms and explain methods and variables used to do it. An
    algorithm like this will be available in all elements, and there
    is not need for additional work.

    All Processing algorithms should extend the QgsProcessingAlgorithm
    class.
    """

    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.

    OUTPUT = 'OUTPUT'
    INPUT = 'INPUT'
    ADDRESSTYPE = 'ADDRESSTYPE'
    EXPRESSION = 'EXPRESSION'

    def flags(self):
        return QgsProcessingAlgorithm.FlagNoThreading

    def initAlgorithm(self, config):
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """
        self.DAWA_ADDRESS_TYPES = [("adresser", self.tr("Adresser")), ("adgangsadresser", self.tr("Adgangsadresser"))]

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Input adressedata'),
                [QgsProcessing.TypeVector]
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.ADDRESSTYPE,
                self.tr('Input adressetype'),
                options=[x[1] for x in self.DAWA_ADDRESS_TYPES], 
                defaultValue=0
            )
        )

        self.addParameter(
            QgsProcessingParameterExpression(
                self.EXPRESSION,
                self.tr('Adresse-udtryk'),
                parentLayerParameterName = self.INPUT
            )
        )

        # We add a feature sink in which to store our processed features (this
        # usually takes the form of a newly created vector layer when the
        # algorithm is run in QGIS).
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Output lag')
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        """
        Here is where the processing itself takes place.
        """

        # Retrieve the feature source and sink. The 'dest_id' variable is used
        # to uniquely identify the feature sink, and must be included in the
        # dictionary returned by the processAlgorithm function.
        source = self.parameterAsSource(parameters, self.INPUT, context)
        exp = self.parameterAsExpression(parameters, "EXPRESSION", context)
        addr_type_ix = self.parameterAsInt(parameters, "ADDRESSTYPE", context)
        addr_type = self.DAWA_ADDRESS_TYPES[addr_type_ix][0]


        id_field_name = self.tr("dawa_id")
        denote_field_name = self.tr("dawa_betegnelse")
        cat_field_name = self.tr("dawa_kategori")
        fields = source.fields()
        fields.append(QgsField(id_field_name, QVariant.String, len=40))
        fields.append(QgsField(denote_field_name, QVariant.String))
        fields.append(QgsField(cat_field_name, QVariant.String, len=1))
        
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT,
                context, fields, QgsWkbTypes.Point, QgsCoordinateReferenceSystem(4326))

        # Compute the number of steps to display within the progress bar and
        # get features from source
        total = 100.0 / source.featureCount() if source.featureCount() else 0
        features = source.getFeatures()
        exp_context = context.expressionContext()
        exp_context.appendScope(source.createExpressionContextScope())
        expression = QgsExpression(exp)
        expression.prepare(exp_context)

        geocoder = DawaGeocoder(addr_type)

        for current, feature in enumerate(features):
            # Stop the algorithm if cancel button has been clicked
            if feedback.isCanceled():
                break
            # Copy src feat to dest feat
            out_feature = QgsFeature(fields)
            for field in source.fields():
                out_feature[field.name()] = feature[field.name()]
            
            # Get address string    
            exp_context.setFeature(feature)
            address = expression.evaluate(exp_context)
            
            try:
            # Geocode it
                geocoded = geocoder.geocode(address)
                if geocoded:
                    out_feature.setGeometry(QgsGeometry(geocoded["accesspoint"]))
                    out_feature[id_field_name] = geocoded["id"]
                    out_feature[cat_field_name] = geocoded["category"]
                    out_feature[denote_field_name] = geocoded["denotation"]
            except:
                #out_feature.setGeometry(QgsGeometry(geocoded["accesspoint"]))
                out_feature[id_field_name] = " "
                out_feature[cat_field_name] = " "
                out_feature[denote_field_name] = " "
                message = "Fejl i en adresse "+ address +"\n"
                #iface.messageBar().pushMessage(message, level=Qgis.Warning, duration=10)
                feedback.pushInfo(message)
            # Add a feature in the sink
            sink.addFeature(out_feature, QgsFeatureSink.FastInsert)

            # Update the progress bar
            feedback.setProgress(int(current * total))

        # Return the results of the algorithm. In this case our only result is
        # the feature sink which contains the processed features, but some
        # algorithms may return multiple feature sinks, calculated numeric
        # statistics, etc. These should all be included in the returned
        # dictionary, with keys matching the feature corresponding parameter
        # or output names.
        return {self.OUTPUT: dest_id}

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'Geokod danske adresser med DAWA'

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr(self.name())

    def group(self):
        """
        Returns the name of the group this algorithm belongs to. This string
        should be localised.
        """
        return self.tr(self.groupId())

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to. This
        string should be fixed for the algorithm, and must not be localised.
        The group id should be unique within each provider. Group id should
        contain lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'Geokodning'

    def shortDescription(self):
        return self.helpString()

    def helpString(self):
        return self.tr("""
        <p>
            Dette plugin er udviklet af <a href="https://www.septima.dk">Septima</a> og anvender <a href="https://dawa.aws.dk/">DAWA</a>s Datavask-API.
        </p>
        <p>
            Med pluginet kan man oversætte en ustruktureret adressetekst til en officiel adresse fra Danmarks Adresseregister (DAR). 
            Det håndterer stavefejl og situationer, hvor den officielle adressebetegnelse er ændret.
        </p>
        <p>
            Pluginet tager imod en adressetekst og returnerer dén adresse, som bedst matcher. Hvis adresseteksten, som skal geokodes, 
            findes i flere felter i attributtabellen (fx vejnavn i et felt, husnummer i et andet felt og postnummer i et tredje felt), 
            så skal disse sættes sammen til et samlet adresseudtryk vha. udtryksbyggeren (klik på epsilon-ikonet). 
        </p>
        <p>
            En gyldig adresse kan skrives på forskellige måder (varianter). Man kan fx vælge at udelade det supplerende bynavn, 
            eller at bruge det forkortede "adresseringsvejnavn" i stedet for det fulde vejnavn. 
        </p>
        <p>
            Bemærk at man skal vælge mellem vask af <b>adresser</b> eller <b>adgangsadresser</b>. Forskellen er at ’adresser’ kan indeholde en etage- og dørbetegnelse, dvs. de går helt til entrédøren. 
            Det gør ’adgangsadresser’ (som i dag hedder ’husnumre’) ikke, de slutter altid ved gade- eller opgangsdøren.
        </p>
        <p>
            Datavask svar angiver hvor sikkert svaret er, i form af en <b>kategori</b> A, B eller C. A indikerer eksakt match. 
            B indikerer et ikke helt eksakt match, men at resultatet stadig er sikkert. C betyder, at resultatet usikkert. Det er vigtigt at gennemgå adresserne, der har fået et 'C', da mange af dem vil være forkerte!
        </p>
        <p>
            Datavask anvender også DAR’s historiske adresser som datagrundlag, således at adresser som er ændret også kan vaskes. 
            Endvidere håndterer datavasken også adresser hvor der er anvendt såkaldte ’stormodtagerpostnumre’ fra PostNord.
        </p>
        <p>
            Læs mere på <a href="https://github.com/Septima/qgis-addresstoolsdk">pluginets GitHub-side</a>.
        </p>
        """)

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return DkGeokoderAlgorithm()
