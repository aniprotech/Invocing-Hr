<?xml version="1.0" encoding="UTF-8"?>
<axsl:stylesheet xmlns:axsl="http://www.w3.org/1999/XSL/Transform" xmlns:dsig="http://www.w3.org/2000/09/xmldsig#" xmlns:hd="http://www.govtalk.gov.uk/CM/envelope" xmlns:nvr="http://www.govtalk.gov.uk/taxation/PAYE/RTI/NINOverificationRequest/1" xmlns:date="http://exslt.org/dates-and-times" xmlns:dyn="http://exslt.org/dynamic" xmlns:exsl="http://exslt.org/common" xmlns:iso="http://purl.oclc.org/dsdl/schematron" xmlns:math="http://exslt.org/math" xmlns:random="http://exslt.org/random" xmlns:regexp="http://exslt.org/regular-expressions" xmlns:sch="http://www.ascc.net/xml/schematron" xmlns:set="http://exslt.org/sets" xmlns:str="http://exslt.org/strings" dsig:dummy-for-xmlns="" exclude-result-prefixes="sch iso" extension-element-prefixes="date dyn math random regexp set str exsl" hd:dummy-for-xmlns="" nvr:dummy-for-xmlns="" version="1.0">

<!--PHASES-->


<!--PROLOG-->
<dsl-rim:namespaceMappings xmlns:dsl-rim="http://www.decisionsoft.com/rim" xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse">
    <dsl-rim:namespaceMapping prefix="hd" uri="http://www.govtalk.gov.uk/CM/envelope"/>
    <dsl-rim:namespaceMapping prefix="dsig" uri="http://www.w3.org/2000/09/xmldsig#"/>
    <dsl-rim:namespaceMapping prefix="nvr" uri="http://www.govtalk.gov.uk/taxation/PAYE/RTI/NINOverificationRequest/1"/>
  </dsl-rim:namespaceMappings>
  <axsl:output xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" indent="yes" method="xml" omit-xml-declaration="no" standalone="yes"/>

<!--KEYS-->


<!--DEFAULT RULES-->


<!--MODE: SCHEMATRON-FULL-PATH-->
<axsl:template match="*" mode="schematron-get-full-path">
    <axsl:apply-templates mode="schematron-get-full-path" select="parent::*"/>
    <axsl:text>/</axsl:text>
    <axsl:variable name="nsuri" select="namespace-uri()"/>
    <axsl:variable xmlns:dsl-rim="http://www.decisionsoft.com/rim" name="prefix" select="document('')//dsl-rim:namespaceMapping[@uri=$nsuri]/@prefix"/>
    <axsl:if test="$prefix">
      <axsl:value-of select="concat($prefix,':')"/>
    </axsl:if>
    <axsl:value-of select="local-name()"/>
    <axsl:variable name="preceding" select="count(preceding-sibling::*[local-name()=local-name(current())                                   and namespace-uri() = namespace-uri(current())])"/>
    <axsl:text>[</axsl:text>
    <axsl:value-of select="1+ $preceding"/>
    <axsl:text>]</axsl:text>
  </axsl:template>
  <axsl:template match="@*" mode="schematron-get-full-path">
    <axsl:apply-templates mode="schematron-get-full-path" select="parent::*"/>
    <axsl:text>/@</axsl:text>
    <axsl:variable name="nsuri" select="namespace-uri()"/>
    <axsl:variable xmlns:dsl-rim="http://www.decisionsoft.com/rim" name="prefix" select="document('')//dsl-rim:namespaceMapping[@uri=$nsuri]/@prefix"/>
    <axsl:if test="$prefix">
      <axsl:value-of select="concat($prefix,':')"/>
    </axsl:if>
    <axsl:value-of select="local-name()"/>
  </axsl:template>
  <!--Strip characters-->
  <axsl:template match="text()" priority="-1"/>

<!--SCHEMA METADATA-->
<axsl:template match="/">
    <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errors">
      <axsl:apply-templates mode="M4" select="/"/>
      <axsl:apply-templates mode="M5" select="/"/>
      <axsl:apply-templates mode="M6" select="/"/>
      <axsl:apply-templates mode="M7" select="/"/>
      <axsl:apply-templates mode="M8" select="/"/>
      <axsl:apply-templates mode="M9" select="/"/>
      <axsl:apply-templates mode="M10" select="/"/>
      <axsl:apply-templates mode="M11" select="/"/>
    </axsl:variable>
    <err:ErrorResponse xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension" SchemaVersion="2.0">
      <axsl:copy-of select="$errors"/>
    </err:ErrorResponse>
  </axsl:template>

<!--SCHEMATRON PATTERNS-->


<!--PATTERN p57-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/nvr:IRenvelope/nvr:IRheader/nvr:Keys/nvr:Key" mode="M4" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="count(../../../../../hd:GovTalkDetails/hd:Keys/hd:Key[@Type = current()/@Type and . = current()]) &gt; 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">5005</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">Keys in the GovTalkDetails do not match those in the IRheader.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>Keys in the IR header must also exist in the GovTalk header with the same value</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M4" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M4" priority="-1"/>
  <axsl:template match="@*|node()" mode="M4" priority="-2">
    <axsl:apply-templates mode="M4" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p56-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/nvr:IRenvelope/nvr:IRheader" mode="M5" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="count(nvr:Keys/nvr:Key) &gt; 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">5004</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">At least one key must exist in the IRheader</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>At least one key must exist in the IRheader</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M5" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M5" priority="-1"/>
  <axsl:template match="@*|node()" mode="M5" priority="-2">
    <axsl:apply-templates mode="M5" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p59-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/nvr:IRenvelope/nvr:NINOverificationRequest/nvr:EmpRefs/nvr:OfficeNo" mode="M6" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../../../nvr:IRheader/nvr:Keys/nvr:Key[@Type = 'TaxOfficeNumber'] = ."/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7821</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The TaxOfficeNumber key within the IRheader must match [HMRCOFFICENUMBER]</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>The TaxOfficeNumber key within the IRheader must match [HMRCOFFICENUMBER]</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M6" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M6" priority="-1"/>
  <axsl:template match="@*|node()" mode="M6" priority="-2">
    <axsl:apply-templates mode="M6" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p60-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/nvr:IRenvelope/nvr:NINOverificationRequest/nvr:EmpRefs/nvr:PayeRef" mode="M7" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../../../nvr:IRheader/nvr:Keys/nvr:Key[@Type = 'TaxOfficeReference'] = ."/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7822</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The TaxOfficeReference key within the IRheader must match [EMPLOYERPAYEREF]</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>The TaxOfficeReference key within the IRheader must match [EMPLOYERPAYEREF]</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M7" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M7" priority="-1"/>
  <axsl:template match="@*|node()" mode="M7" priority="-2">
    <axsl:apply-templates mode="M7" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p62-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/nvr:IRenvelope/nvr:NINOverificationRequest/nvr:Employee/nvr:EmployeeDetails/nvr:Address/nvr:ForeignCountry" mode="M8" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(count(../nvr:Line)) &gt;= 2"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7825</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">There is an entry in [FOREIGNCOUNTRY]. Please complete at least two [ADDRESSLINE] </axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [FOREIGNCOUNTRY] is present, at least two [ADDRESSLINE] should be present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M8" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M8" priority="-1"/>
  <axsl:template match="@*|node()" mode="M8" priority="-2">
    <axsl:apply-templates mode="M8" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p63-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/nvr:IRenvelope/nvr:NINOverificationRequest/nvr:Employee/nvr:EmployeeDetails/nvr:BirthDate" mode="M9" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space((.))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">5001</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The Date must be today or earlier. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>The Date of Birth must be today or earlier.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(date:add(normalize-space(date:date()),normalize-space(&quot;-P130Y&quot;)))) div 86400) &lt; round(date:seconds(normalize-space((.))) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7826</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">[DATEOFBIRTH] must be later than 130 years before today's date. Please check </axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>Must be later than 130 years before today</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M9" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M9" priority="-1"/>
  <axsl:template match="@*|node()" mode="M9" priority="-2">
    <axsl:apply-templates mode="M9" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p61-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/nvr:IRenvelope/nvr:NINOverificationRequest/nvr:Employee/nvr:EmployeeDetails" mode="M10" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="nvr:NINO             or               count(nvr:Address/nvr:Line) &gt;= 2"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7823</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">There is no entry in [NINO]. Please complete at least two [ADDRESSLINE] </axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>At least two [ADDRESSLINE] should be present if not ( [NINO] is present )</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="nvr:Name/nvr:Fore or nvr:Name/nvr:Initials"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7824</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">There must be an entry in either [FORENAME] or [INITIALS]</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>At least one of [FORENAME] and [INITIALS] must be present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M10" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M10" priority="-1"/>
  <axsl:template match="@*|node()" mode="M10" priority="-2">
    <axsl:apply-templates mode="M10" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p58-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/nvr:IRenvelope/nvr:NINOverificationRequest" mode="M11" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../../../hd:Header/hd:MessageDetails/hd:Class = 'HMRC-PAYE-RTI-NVR'           or           ../../../hd:Header/hd:MessageDetails/hd:Class = 'HMRC-PAYE-RTI-NVR-TIL'"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7839</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">Valid message classes for a NINO Verification Request are HMRC-PAYE-RTI-NVR and HMRC-PAYE-RTI-NVR-TIL.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>Valid message classes for a NINO Verification Request are HMRC-PAYE-RTI-NVR and HMRC-PAYE-RTI-NVR-TIL.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(count(nvr:Employee)) &lt;= 100"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7827</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">You can only include between 1 and 100 [EMPLOYEE]s in each NINO Verification request.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[EMPLOYEE] may repeat up to 100 times.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M11" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M11" priority="-1"/>
  <axsl:template match="@*|node()" mode="M11" priority="-2">
    <axsl:apply-templates mode="M11" select="@*|node()"/>
  </axsl:template>
</axsl:stylesheet>
